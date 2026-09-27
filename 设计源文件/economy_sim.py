# -*- coding: utf-8 -*-
"""
《汴河两岸》经营数值核算：蒙特卡洛 + 离散事件模拟

用法
    python economy_sim.py <菜品与家宴数据.json> [--runs 200] [--seed 1] [--prices current|calibrated]
                          [--banquet accept|decline] [--force-good 0.7] [--skill 0.5] [--price-scale 1.0]
                          [--calibrate] [--out results.json]
    结果要逐位复现时先设 PYTHONHASHSEED=0（集合的遍历顺序会影响随机数的使用顺序）。

模型（每条都对应《玩法与数值》《菜谱与食材》和 23 道菜 JSON 里的规则）
  1. 一局营业是 6 分钟的离散事件模拟。客人成组到店（泊松过程，平均间隔按声望阶段，乘口碑系数），
     有空桌就入座，没有就在门口最多等 10 秒后离开。每组点单遵守 JSON 的推荐规则：不点带避开标签的菜，
     整桌价格不超过整桌预算，整桌饱腹不低于目标的 90%，多数人口味合适；在满足条件的组合里按随机效用
     （口味、分量、价格、档次、时令权重 + Gumbel 噪声）选一个。工人各点各的；学生、带孩子的家人、
     两位妇人和名流整桌合点，份数约为人数的四分之三。
  2. 后厨：一口灶一次做一份，灶台等级要够。亲手做的菜要玩家花 1.5 秒投料、0.5 秒出炉；出炉时刻
     T 后的反应延迟 δ = 0.15 + 指数分布（均值 0.5 秒），玩家正在忙别的就再往后推；δ ≤ 0.7 秒是完美
     （高等菜亲手做为仙味），≤ 3 秒是完美或不错，> 3 秒糊掉重做；2% 提早出炉成次等。同一道菜从
     第二关起亲手做好满 3 / 8 / 12 次后自动做：不占玩家，到点出炉，简单、中等完美，高等不错；自动做同时最多占
     2 口灶（PARAMS['auto_cap']），超出的排队，玩家有空、有空灶时亲手接下。
     仙家密法按开灶时店里的客人数缩短出餐时间。
  3. 前堂：第二关后有小二，负责点单（2 秒）、上菜（1.5 秒）和追跑单；每人照看约 3 张桌，
     超过时动作按比例变慢。没有小二时玩家自己点单（3 秒）、上菜（1.5 秒）。
  4. 耐心从点完单算起：按最难的菜 25 / 35 / 45 秒，每多一人加 5 秒；超时评价降一档，再过 15 秒没
     上齐就走（0 经验、不付钱）。用餐 30 / 40 / 50 秒后结账。评价按出品表抽取，口味或分量合适好评
     ＋15 个百分点（只加一次）；后世菜前 20 份按新菜反应（做过试味 ＋10）。经验 6 / 4 / 2。
  5. 营业日之外：每天早上按预测用量加 25% 余量采购（整筐折扣、砍价、坏料、库存上限），验货丢坏料
     （3 级小二开自动验货时漏检 5%，漏掉的坏料出炉时作废重做），晚上剩货按过夜损耗扣。每 10 天发
     工钱。按"哪里不够买哪里"的贪心策略添置桌子、扩建、灶台和灶台升级，并留出当天的食材钱和工钱。
     事件：跑单、名流来访、仙人（仙家密法）、时令、大鱼头每天 0–4 个、佛跳墙只接预约、名流家宴。
  6. 每组设定跑 N 次（固定种子），报告中位数和 P10–P90。

所有经营数值都在下面的 PARAMS 里；菜品、食材、调料、酒和顾客数据从 JSON 读取。
PARAMS['price_sets'] 有两套设备价：current（《玩法与数值》04 原价）和 calibrated（标定后采用的价）。
PARAMS['stages']['inventory'] 是建议的库存上限；原值在 PARAMS['inventory_original']（--inventory original）。
标定方法：在"扩建前的设备（一楼桌子、前 5 口灶、初→中升级）"和"扩建及以后的设备"两组价格上做网格搜索，
代价 = 各阶段中位首日与目标（二级 6、三级 8、四级 11、五级 14）的偏差平方 + 买满时间超出 16–20 天的
平方 + 四级前没扩建的比例 + 改价幅度；在代价接近的方案里取改动最少的一组（只动扩建及以后的设备）。
"""
import argparse
import heapq
import json
import math
import random
import statistics
import sys
import time
from collections import defaultdict, deque
from itertools import combinations, combinations_with_replacement

STAGE_NAMES = ['一级①', '一级②', '一级③', '二级', '三级', '四级', '五级']

PARAMS = {
    # ---- 声望阶段（固定）----
    'stages': {
        'xp':        [0, 60, 150, 300, 650, 1200, 2100],
        'cap':       [12, 18, 24, 36, 54, 72, 96],       # 当日最多来客（累计人数）
        'interval':  [90, 60, 45, 30, 20, 15, 11],       # 有空桌时平均每组间隔（秒）
        'tables':    [1, 2, 3, 4, 6, 8, 12],             # 桌子上限（第 5、6 张要扩建）
        'stoves':    [1, 2, 4, 5, 8, 10, 12],            # 灶台上限
        'waiters':   [1, 1, 1, 2, 2, 3, 4],              # 小二上限（第二关后才有）
        'inventory': [60, 60, 60, 100, 180, 240, 320],   # 主食材库存上限（份）：建议值；原值见 inventory_original
        'level':     [1, 1, 1, 2, 3, 4, 5],
    },
    'inventory_original': [40, 40, 40, 80, 120, 180, 240],  # 《玩法与数值》06 的原值，按 23 道菜会每天卡库存
    'reputation': {'base': 0.6, 'slope': 0.4},            # 口碑系数 = 0.6 + 0.4 × 前一天好评率
    'business_seconds': 360,
    'door_wait': 10,
    'start_cash': 300,
    # ---- 价格（旋钮）----
    'price_sets': {
        'current': {
            'table': {2: 60, 3: 120, 4: 250, 7: 400, 8: 400, 9: 600, 10: 600, 11: 600, 12: 600},
            'expansion': 1200,     # 三级起，含第 5、6 张桌，次日开放
            'stove': {2: 50, 3: 80, 4: 80, 5: 150, 6: 250, 7: 250, 8: 250, 9: 400, 10: 400, 11: 500, 12: 500},
            'upgrade': {2: 150, 3: 600},   # 初→中（二级起）；中→高（四级起）
        },
        # 标定结果（见 scratchpad 的 calib*.py）：只改扩建以后的设备，一楼的桌子、前 5 口灶和中等升级不动
        'calibrated': {
            'table': {2: 60, 3: 120, 4: 250, 7: 250, 8: 250, 9: 350, 10: 350, 11: 350, 12: 350},
            'expansion': 700,
            'stove': {2: 50, 3: 80, 4: 80, 5: 150, 6: 150, 7: 150, 8: 150, 9: 250, 10: 250, 11: 300, 12: 300},
            'upgrade': {2: 150, 3: 350},
        },
    },
    # ---- 员工 ----
    'wages': {1: 300, 2: 600, 3: 900},      # 每月（10 个游戏日）；3 级原为 1000，9-26 改为 900
    'waiter_fee': 60,
    'waiter_upgrade_fee': {2: 150, 3: 500},
    'waiter_level2_days': 5,
    'first_waiter_day': 3,                   # 第二关（第 2 天）后入职，第 3 天起全天在岗
    'auto_inspect_miss': 0.05,
    # ---- 做菜 ----
    'auto_cook_counts': {1: 3, 2: 8, 3: 12},
    'auto_count_from_day': 2,                # 第二关（第 2 天第一桌）起计数
    'auto_cap': [2, 2, 2, 2, 2, 2, 2],       # 自动做同时最多占几口灶（按阶段：一级①…五级）；None＝不限。9-26 定为 2 口
    'xian_rates': [(24, 0.50), (16, 0.40), (12, 0.30), (8, 0.20), (4, 0.10), (1, 0.05)],
    'xian_delay_days': 2,                    # 升到二级后约第 2 天仙人来，亲手做好即得仙家密法
    'patience': {1: 25, 2: 35, 3: 45},
    'patience_per_extra': 5,
    'patience_grace': 15,
    'dine': {1: 30, 2: 40, 3: 50},
    'actions': {'player_order': 3.0, 'player_serve': 1.5, 'start': 1.5, 'takeout': 0.5,
                'waiter_order': 2.0, 'waiter_serve': 1.5, 'chase': 8.0, 'tables_per_waiter': 3},
    'skill': {'delta_min': 0.15, 'delta_mean': 0.5, 'early': 0.02},
    # ---- 评价与经验 ----
    'review_table': {'immortal': (1.0, 0.0, 0.0), 'perfect': (0.70, 0.25, 0.05), 'good': (0.60, 0.35, 0.05),
                     'under': (0.20, 0.40, 0.40), 'burnt': (0.0, 0.20, 0.80)},
    'match_bonus': 0.15,
    'novel': {'portions': 20, 'base': (0.65, 0.25, 0.10), 'perfect': 0.05, 'immortal': 0.20,
              'under': -0.15, 'tasting': 0.10, 'floor': 0.51, 'tasting_portions': 3},
    'xp': {'good': 6, 'normal': 4, 'bad': 2},
    # ---- 顾客 ----
    'mix': {'worker': 0.40, 'women': 0.30, 'student': 0.30},
    'group_sizes': {'worker': [(2, 0.25), (3, 0.50), (4, 0.25)],
                    'student': [(2, 0.15), (3, 0.25), (4, 0.60)],
                    'women': [(('family',), 0.35), (('family', 'family'), 0.30),
                              (('family', 'child'), 0.25), (('family', 'child', 'child'), 0.10)]},
    'women_from_stage': 1, 'students_from_day': 2,
    'jiangjiu': {'from_level': 3, 'share': 0.20, 'budget_mult': 2.0},
    'celebrity': {'from_stage': 3, 'student_good': 20, 'daily': 0.25, 'companions': (1, 2)},
    'drinks': {'jiangjiu': 0.30, 'celebrity': 0.70},
    'utility': {'taste': 1.2, 'portion': 0.8, 'price': 1.0, 'price_jiangjiu': 0.4, 'tier': 0.12,
                'tier_jiangjiu': 0.35, 'novel_celebrity': 0.25, 'pair_penalty': 0.3, 'dup_penalty': 0.4,
                'noise': 0.6, 'pool': 40},
    # ---- 事件 ----
    'runners': {'from_stage': 3, 'p_low': 0.40, 'p_high': 0.50, 'two_share_high': 0.30, 'catch_window': 5},
    'seasons': {'days': 10, 'cold_noodle': 'D11', 'crystal': 'D05', 'boost': 2.0, 'off': 0.5, 'price_mult': 1.2},
    'fish_head_daily': (0, 4),
    'reservation': {'from_stage': 6, 'dish': 'D21', 'per_day': (1, 2), 'size': (2, 4)},
    'banquet': {'from_stage': 4, 'daily': 0.20, 'cooldown_business_days': 3, 'p_host_met': 0.90,
                'score_mean': 94.0, 'score_sd': 4.0, 'capped_score': 65.0, 'buff_days': 2, 'buff_mult': 1.1,
                # 经费三档随机出现（各 1/3）：经费越紧，满意酬谢越高；按"看提示调整菜单"的玩家，超支很少，模型里不计
                'difficulty_bonus_mult': {'宽裕': 1.0, '适中': 1.25, '紧张': 1.5}},
    # ---- 采购 ----
    'buy': {'buffer': 0.25, 'ema': 0.5, 'bargain_cut': 0.10, 'bargain_p': 0.60, 'floor': 0.70,
            'bulk': [(20, 0.8), (10, 0.9)], 'bulk_bad': 0.05, 'new_dish_prior': 0.04, 'min_per_dish': 2},
    # ---- 添置策略 ----
    'policy': {'fill_cushion': 50, 'reserve_extra': 30, 'medium_share': 0.5, 'high_share': 0.34},
    'horizon': 60,
}

VENDOR = {  # 采购摊位：每个摊位每天砍一次价
    'flour': 'mian', 'rice': 'mian', 'rice_prep': 'mian', 'pancake': 'mian',
    'radish': 'cai', 'gourd': 'cai', 'greens': 'cai', 'bamboo': 'cai', 'perilla': 'cai', 'mushroom': 'cai',
    'pork': 'rou', 'kidney': 'rou', 'skin': 'rou', 'stock': 'rou', 'lamb': 'rou',
    'chicken': 'qin', 'duck': 'qin', 'egg': 'qin', 'wing': 'qin',
    'tofu': 'doufu', 'fish': 'yu', 'mandarin_fish': 'yu', 'crab': 'yu', 'fish_head': 'yu',
    'pickle_base': 'gan', 'sauerkraut': 'gan', 'seafood': 'gan',
}
BULK_CATS = {'grain', 'meat', 'vegetable', 'fish', 'preserved'}


# ------------------------------------------------------------------ 数据
class Data:
    def __init__(self, path):
        J = json.load(open(path, encoding='utf-8'))
        self.J = J
        self.ing = {i['id']: i for i in J['ingredients']}
        self.profiles = J['customer_profiles']
        self.dishes = {}
        for r in J['recipes'] + J['recipe_variants']:
            d = {
                'id': r['id'], 'name': r['name'], 'base': r.get('base_recipe_id', r['id']),
                'tier': r['difficulty'], 'stove': r['required_stove_tier'], 'secs': float(r['cook_seconds']),
                'price': r['default_price'] / 100.0,
                'seas_cost': sum(self.ing[k]['base_unit_cost'] * q for k, q in r['seasonings'].items()) / 100.0,
                'ings': dict(r['ingredients']), 'sat': r['satiety'], 'temp': r['temperature'],
                'tags': frozenset(r['taste_tags']), 'staple': r['is_staple'], 'novel': r['is_novel_recipe'],
                'xp': r['unlock']['cumulative_xp'], 'flags': tuple(r['unlock']['required_flags']),
                'variant': 'base_recipe_id' in r,
                'modern': frozenset(k for k in r['ingredients'] if self.ing[k]['category'] == 'modern'),
                'cost': r['base_cost'] / 100.0,
            }
            d['match'] = d['tags'] | {d['temp']}
            self.dishes[d['id']] = d
        self.wines = [i for i in J['ingredients'] if i['category'] == 'wine']
        self.modern = [i['id'] for i in J['ingredients'] if i['category'] == 'modern']
        self.portal_caps = J['rules']['portal_normal']['caps']   # {'1_3':6,'2':10,...}（schema 1.2 以前键名是 1_stage3）

    def portal_cap(self, stage):
        lvl = PARAMS['stages']['level'][stage]
        if lvl == 1:
            return self.portal_caps.get('1_3', self.portal_caps.get('1_stage3'))
        return self.portal_caps[str(lvl)]


def stage_of(xp):
    s = 0
    for i, t in enumerate(PARAMS['stages']['xp']):
        if xp >= t:
            s = i
    return s


def xian_rate(n):
    for th, r in PARAMS['xian_rates']:
        if n >= th:
            return r
    return 0.0


def choice_w(rng, pairs):
    x = rng.random()
    acc = 0.0
    for v, w in pairs:
        acc += w
        if x <= acc:
            return v
    return pairs[-1][0]


# ------------------------------------------------------------------ 点单：候选组合池（按菜单 + 客人签名缓存）
POOL_CACHE = {}


def build_pool(data, menu, season_w, season_p, sig):
    """sig = (kind, members, budget, k, jj, celeb)。返回 (feasible_list, fallback_list)，元素为
    (base_util, dish_ids, price, sat, taste_n, strict)。"""
    kind, members, budget, k, jj, celeb = sig
    U = PARAMS['utility']
    prof = data.profiles
    avoid = set()
    for m in members:
        avoid |= set(prof[m]['avoid'])
    prefs = [set(prof[m]['prefer']) for m in members]
    target = sum(prof[m]['target_satiety'] for m in members)
    n = len(members)
    B = budget if budget is not None else 1e9
    cands = []
    for did in menu:
        d = data.dishes[did]
        p = d['price'] * season_p.get(did, 1.0)
        if d['tags'] & avoid or p > B:
            continue
        cands.append((did, p, d['sat'], d['tier'], d['novel'], d['match'], math.log(season_w.get(did, 1.0))))
    sizes = [k, k + 1] if kind == 'S' else [1, 2]
    pw = 0.0 if celeb else (U['price_jiangjiu'] if jj else U['price'])
    tw = U['tier_jiangjiu'] if (jj or celeb) else U['tier']
    feas, fall = [], []
    for sz in sizes:
        if sz > len(cands) or sz < 1:
            continue
        for combo in combinations_with_replacement(cands, sz):
            price = sum(c[1] for c in combo)
            if price > B:
                continue
            sat = sum(c[2] for c in combo)
            matched = 0
            for pf in prefs:
                if any(c[5] & pf for c in combo):
                    matched += 1
            if celeb:
                matched = n
            util = (U['taste'] * matched / n + U['portion'] * min(1.0, sat / (0.9 * target))
                    - pw * price / (B if budget is not None else 100.0)
                    + tw * sum(c[3] - 1 for c in combo)
                    + U['noise'] * sum(c[6] for c in combo))
            if celeb:
                util += U['novel_celebrity'] * sum(1 for c in combo if c[4])
            if kind == 'I' and sz == 2:
                util -= U['pair_penalty']
            dups = sz - len(set(c[0] for c in combo))
            if dups:
                util -= U['dup_penalty'] * dups
            ids = tuple(c[0] for c in combo)
            ok = sat >= 0.9 * target and matched * 2 >= n and matched >= 1
            strict = sat >= 0.9 * target and matched == n
            rec = (util, ids, price, sat, matched, strict)
            (feas if ok else fall).append(rec)
    feas.sort(key=lambda r: -r[0])
    fall.sort(key=lambda r: -r[0])
    return feas[:U['pool']], fall[:10]


def get_pool(data, menu_key, menu, season_w, season_p, sig):
    key = (menu_key, sig)
    p = POOL_CACHE.get(key)
    if p is None:
        p = build_pool(data, menu, season_w, season_p, sig)
        if len(POOL_CACHE) > 60000:
            POOL_CACHE.clear()
        POOL_CACHE[key] = p
    return p


def gumbel(rng):
    return -math.log(-math.log(rng.random() + 1e-12) + 1e-12)


def make_combo_ok(data, stock, tent=None):
    def combo_ok(ids):
        need = defaultdict(float)
        for did in ids:
            for k, q in data.dishes[did]['ings'].items():
                need[k] += q
        for k, q in need.items():
            have = stock.get(k, 0) - (tent[k] if tent is not None else 0)
            if have < q:
                return False
        return True
    return combo_ok


def pick_order(data, rng, menu_key, menu, season_w, season_p, sig, available, combo_ok):
    pool = get_pool(data, menu_key, menu, season_w, season_p, sig)
    rec, ok = pick_from_pool(rng, pool, combo_ok)
    feasible_menu = bool(pool[0])
    if rec is None or not ok:
        avail_menu = [d for d in menu if available(d)]
        if len(avail_menu) < len(menu):
            pool2 = get_pool(data, (menu_key, tuple(avail_menu)), avail_menu, season_w, season_p, sig)
            rec2, ok2 = pick_from_pool(rng, pool2, combo_ok)
            if rec2 is not None and (ok2 or rec is None):
                rec, ok = rec2, ok2
    return rec, ok, feasible_menu


def pick_from_pool(rng, pool, combo_ok):
    feas, fall = pool
    noise = PARAMS['utility']['noise']
    best, bu = None, -1e9
    for rec in feas:
        if not combo_ok(rec[1]):
            continue
        u = rec[0] + noise * gumbel(rng)
        if u > bu:
            best, bu = rec, u
    if best is not None:
        return best, True
    for rec in fall:
        if combo_ok(rec[1]):
            return rec, False
    return None, False


# ------------------------------------------------------------------ 一局营业
class Group:
    __slots__ = ('gid', 'kind', 'members', 'size', 'budget', 'jj', 'celeb', 'arrive', 'seated', 'order_t',
                 'patience', 'tasks_total', 'tasks_done', 'tasks_cancel', 'served', 'left', 'late', 'dishes',
                 'person_dishes', 'bill', 'drinks', 'hard', 'feasible', 'spend', 'table', 'reserved_order',
                 'runner', 'type', 'drink_cost')

    def __init__(self, gid):
        self.gid = gid
        self.seated = None
        self.order_t = None
        self.served = None
        self.left = False
        self.late = False
        self.dishes = []          # [(dish_id, quality)]
        self.person_dishes = None  # 工人：每人自己的菜
        self.tasks_total = 0
        self.tasks_done = 0
        self.tasks_cancel = 0
        self.bill = 0.0
        self.drinks = 0.0
        self.hard = 1
        self.feasible = True
        self.spend = 0.0
        self.runner = 0
        self.reserved_order = None
        self.drink_cost = 0.0


class Task:
    __slots__ = ('dish', 'group', 'auto', 'stove', 'T', 'hidden_bad', 'person', 'state', 'pre', 'q_t')

    def __init__(self, dish, group, auto, person=None):
        self.dish = dish
        self.group = group
        self.auto = auto
        self.stove = None
        self.T = None
        self.hidden_bad = False
        self.person = person
        self.state = 'queued'
        self.pre = False


class DaySim:
    def __init__(self, camp, rng):
        self.c = camp
        self.rng = rng

    def run(self):
        c, rng, P = self.c, self.rng, PARAMS
        data = c.data
        A = P['actions']
        st = c.stage
        ev = []
        seq = [0]

        def push(t, kind, obj=None):
            seq[0] += 1
            heapq.heappush(ev, (t, seq[0], kind, obj))

        # ---- 今日菜单
        menu = c.today_menu
        menu_key = c.today_menu_key
        season_w, season_p = c.season_w, c.season_p
        stock = c.stock_avail           # dict ingredient -> units usable today（已扣预留）
        dish_left = {}                  # 有日上限的菜（大鱼头）

        def available(did):
            d = data.dishes[did]
            for k, q in d['ings'].items():
                if stock.get(k, 0) < q:
                    return False
            return True

        def reserve(did):
            for k, q in data.dishes[did]['ings'].items():
                stock[k] = stock.get(k, 0) - q
                c.used[k] += q

        def unreserve(did):
            for k, q in data.dishes[did]['ings'].items():
                stock[k] = stock.get(k, 0) + q
                c.used[k] -= q

        # ---- 桌、灶、人
        n_tables = c.tables_open
        free_tables = n_tables
        stoves = [{'tier': t, 'busy': None} for t in c.stove_tiers]
        n_waiters = len(c.waiters)
        waiter_busy = [0.0] * n_waiters
        slow = max(1.0, n_tables / (A['tables_per_waiter'] * n_waiters)) if n_waiters else 1.0
        player_busy = [0.0]
        req_orders = deque()
        req_serves = deque()
        kitchen = deque()               # auto 任务等灶
        starts = deque()                # 手工任务等玩家
        takeouts = []                   # heap (T, seq, task)
        door = deque()
        seated_guests = [0]
        stats = c.day_stats
        xian_on = c.xian_active
        cap = P['auto_cap'][st] if P['auto_cap'] else None

        planned = c.planned_visitors
        lam = (planned / max(1, P['stages']['cap'][st])) / P['stages']['interval'][st]
        groups = []

        # ---- 生成到店
        t = 0.0
        arrived = 0
        first_special = None
        if c.day == 1:
            first_special = ('worker', 3)
        elif c.day == 2:
            first_special = ('student', 4)
        gid = 0
        while True:
            if first_special is not None:
                t = 5.0
            else:
                t += rng.expovariate(lam) if lam > 0 else 1e9
            if t >= P['business_seconds'] or arrived >= planned:
                break
            g = Group(gid)
            gid += 1
            if first_special is not None:
                typ, sz = first_special
                first_special = None
            else:
                typ = c.sample_type(rng)
                sz = None
            c.fill_group(g, typ, sz, rng)
            if arrived + g.size > planned:          # 最后一组不超过当日上限
                keep = planned - arrived
                if keep <= 0:
                    break
                g.members = g.members[:keep]
                g.size = keep
                if g.budget is not None:
                    g.budget = sum(data.profiles[m]['budget_wen'] for m in g.members) *                         (PARAMS['jiangjiu']['budget_mult'] if g.jj else 1.0)
            g.arrive = t
            arrived += g.size
            groups.append(g)
            push(t, 'arr', g)
        # 名流来访
        if c.celebrity_today:
            g = Group(gid)
            gid += 1
            c.fill_group(g, 'celebrity', None, rng)
            g.arrive = rng.uniform(30, 300)
            groups.append(g)
            push(g.arrive, 'arr', g)
        # 预约（佛跳墙）
        for _ in range(c.reservations_today):
            g = Group(gid)
            gid += 1
            c.fill_group(g, 'reservation', None, rng)
            g.arrive = rng.uniform(60, 300)
            groups.append(g)
            push(g.arrive, 'arr', g)
        stats['arrived'] += sum(g.size for g in groups)
        stats['arrived_ordinary'] += arrived

        # 跑单
        runner_times = []
        if st >= P['runners']['from_stage'] and n_waiters > 0:
            R = P['runners']
            if st >= 5:
                if rng.random() < R['p_high']:
                    runner_times = [rng.uniform(90, 330)] * (2 if rng.random() < R['two_share_high'] else 1)
            else:
                if rng.random() < R['p_low']:
                    runner_times = [rng.uniform(90, 330)]
            runner_times.sort()

        # ---------------- 动作与调度
        def cook_time(d):
            base = data.dishes[d]['secs']
            if xian_on:
                base *= (1.0 - xian_rate(seated_guests[0]))
            return base

        def free_stove(tier):
            best = None
            for s in stoves:
                if s['busy'] is None and s['tier'] >= tier:
                    if best is None or s['tier'] < best['tier']:
                        best = s
            return best

        def consume(task):
            # 预留时已扣库存；这里判断是否用到漏检的坏料
            if c.hidden_bad_rate > 0:
                for k in data.dishes[task.dish]['ings']:
                    if c.hidden.get(k, 0) >= 1 and rng.random() < c.hidden_bad_share.get(k, 0.0):
                        task.hidden_bad = True
                        c.hidden[k] -= 1
                        break
            stats['seas_cost'] += data.dishes[task.dish]['seas_cost']

        def n_auto_running():
            return sum(1 for s in stoves if s['busy'] is not None and s['busy'].auto)

        def start_auto(tnow, task, s):
            stats['auto_wait'] += tnow - task.q_t
            stats['auto_started'] += 1
            task.stove = s
            s['busy'] = task
            task.state = 'cooking'
            consume(task)
            task.T = tnow + cook_time(task.dish)
            push(task.T, 'auto_done', task)

        def dispatch(tnow):
            # 1) 自动做
            if kitchen:
                keep = deque()
                n_auto = n_auto_running()
                while kitchen:
                    task = kitchen.popleft()
                    if task.state == 'cancel':
                        continue
                    if cap is not None and n_auto >= cap:
                        keep.append(task)
                        continue
                    s = free_stove(data.dishes[task.dish]['stove'])
                    if s is None:
                        keep.append(task)
                        continue
                    start_auto(tnow, task, s)
                    n_auto += 1
                kitchen.extend(keep)
            # 2) 小二
            for i in range(n_waiters):
                if waiter_busy[i] > tnow + 1e-9:
                    continue
                if req_serves:
                    g = req_serves.popleft()
                    dur = A['waiter_serve'] * slow
                    waiter_busy[i] = tnow + dur
                    push(tnow + dur, 'served', g)
                elif req_orders:
                    g = req_orders.popleft()
                    dur = A['waiter_order'] * slow
                    waiter_busy[i] = tnow + dur
                    push(tnow + dur, 'ordered', g)
            # 3) 玩家
            player_try(tnow)

        def player_try(tnow):
            if player_busy[0] > tnow + 1e-9:
                return
            nxt = takeouts[0][0] if takeouts else 1e18
            if takeouts and nxt <= tnow + 1e-9:
                T, _, task = heapq.heappop(takeouts)
                S = PARAMS['skill']
                delta = S['delta_min'] + rng.expovariate(1.0 / max(1e-6, S['delta_mean'] - S['delta_min'] + 1e-9)) \
                    if S['delta_mean'] > S['delta_min'] else S['delta_min']
                tk = tnow + delta
                L = tk - task.T
                d = data.dishes[task.dish]
                if rng.random() < S['early']:
                    q = 'under'
                elif L <= 0.7:
                    q = 'immortal' if d['tier'] == 3 else 'perfect'
                elif L <= 3.0:
                    q = 'perfect' if d['tier'] < 3 else 'good'
                else:
                    q = 'burnt'
                player_busy[0] = tk + A['takeout']
                stats['player_busy_s'] += tk + A['takeout'] - tnow
                push(tk + A['takeout'], 'tk_done', (task, q))
                return
            horizon = nxt - tnow
            cand = []
            if n_waiters == 0:
                if req_serves:
                    cand.append(('serve', A['player_serve']))
                if req_orders:
                    cand.append(('order', A['player_order']))
            if starts:
                cand.append(('start', A['start']))
            for what, dur in cand:
                if dur > horizon + 0.3:
                    continue
                if what == 'serve':
                    g = req_serves.popleft()
                    player_busy[0] = tnow + dur
                    stats['player_busy_s'] += dur
                    push(tnow + dur, 'served', g)
                    return
                if what == 'order':
                    g = req_orders.popleft()
                    player_busy[0] = tnow + dur
                    stats['player_busy_s'] += dur
                    push(tnow + dur, 'ordered', g)
                    return
                if what == 'start':
                    # 找第一个有灶可用的手工任务
                    for _ in range(len(starts)):
                        task = starts[0]
                        if task.state == 'cancel':
                            starts.popleft()
                            continue
                        s = free_stove(data.dishes[task.dish]['stove'])
                        if s is None:
                            starts.rotate(-1)
                            continue
                        starts.popleft()
                        task.stove = s
                        s['busy'] = task
                        task.state = 'starting'
                        player_busy[0] = tnow + dur
                        stats['player_busy_s'] += dur
                        push(tnow + dur, 'begin', task)
                        return
                    stats['stove_block'] += 1
            # 自动做占满上限时，玩家有空就亲手接下排队的菜
            if cap is not None and kitchen and A['start'] <= horizon + 0.3 and n_auto_running() >= cap:
                for _ in range(len(kitchen)):
                    task = kitchen[0]
                    if task.state == 'cancel':
                        kitchen.popleft()
                        continue
                    s = free_stove(data.dishes[task.dish]['stove'])
                    if s is None:
                        kitchen.rotate(-1)
                        continue
                    kitchen.popleft()
                    task.auto = False
                    stats['takeover_plates'] += 1
                    stats['auto_wait'] += tnow - task.q_t
                    stats['auto_started'] += 1
                    task.stove = s
                    s['busy'] = task
                    task.state = 'starting'
                    player_busy[0] = tnow + A['start']
                    stats['player_busy_s'] += A['start']
                    push(tnow + A['start'], 'begin', task)
                    return
            if takeouts:
                push(max(tnow, nxt), 'wake', None)

        def enqueue_task(tnow, task):
            task.q_t = tnow
            if task.auto:
                kitchen.append(task)
            else:
                starts.append(task)

        def make_tasks(tnow, g):
            for did, person in g.reserved_order:
                d = data.dishes[did]
                auto = c.is_auto(d['base'])
                task = Task(did, g, auto, person)
                g.tasks_total += 1
                enqueue_task(tnow, task)

        def seat(tnow, g):
            nonlocal free_tables
            free_tables -= 1
            g.seated = tnow
            seated_guests[0] += g.size
            if g.kind == 'reservation':
                # 预约：菜提前做好，入座即点（仍走上菜流程）
                push(tnow, 'ordered', g)
            else:
                req_orders.append(g)
            dispatch(tnow)

        def leave_table(tnow, g):
            nonlocal free_tables
            free_tables += 1
            seated_guests[0] -= g.size
            while door:
                w = door.popleft()
                if w.left or w.seated is not None:
                    continue
                if tnow <= w.arrive + P['door_wait'] + 1e-9:
                    seat(tnow, w)
                    break
            dispatch(tnow)

        def finish_group(tnow, g):
            # 结账：评价、经验、收入
            stats['groups_paid'] += 1
            R = PARAMS['review_table']
            N = PARAMS['novel']
            prof = data.profiles
            target = sum(prof[m]['target_satiety'] for m in g.members)
            served = [d for d, q in g.dishes]
            portion_ok = sum(data.dishes[d]['sat'] for d in served) >= 0.9 * target if served else False
            runners = g.runner
            share = (g.bill + g.drinks) / g.size
            for idx, m in enumerate(g.members):
                if g.person_dishes is not None:
                    mine = [x for x in g.dishes if x[0] in g.person_dishes[idx]] or g.dishes
                    own_sat = sum(data.dishes[d]['sat'] for d, q in mine)
                    p_ok = own_sat >= 0.9 * prof[m]['target_satiety']
                else:
                    mine = g.dishes
                    p_ok = portion_ok
                if not mine:
                    continue
                did, q = mine[int(rng.random() * len(mine))]
                d = data.dishes[did]
                pf = set(prof[m]['prefer'])
                taste_ok = g.celeb or any(data.dishes[x]['match'] & pf for x, _ in mine)
                if runners > 0 and idx == len(g.members) - 1:
                    # 跑单客
                    runners -= 1
                    if c.try_chase(tnow, waiter_busy):
                        stats['runner_caught'] += 1
                        stats['paid_customers'] += 1
                        c.add_review('bad', m, g)
                    else:
                        stats['runner_lost'] += 1
                        stats['revenue'] -= share
                        stats['lost_customers'] += 1
                    continue
                if d['novel'] and c.novel_count[d['base']] < N['portions'] and c.novel_count_review.get(d['base'], 0) < N['portions']:
                    c.novel_count_review[d['base']] = c.novel_count_review.get(d['base'], 0) + 1
                    wel = N['base'][0] + N['tasting']
                    if q == 'perfect':
                        wel += N['perfect']
                    elif q == 'immortal':
                        wel += N['immortal']
                    elif q == 'under':
                        wel += N['under']
                    wel = min(1.0, max(N['floor'], wel))
                    rest = 1.0 - wel
                    probs = [wel, rest * 25 / 35, rest * 10 / 35]
                else:
                    probs = list(R[q])
                    if taste_ok or p_ok:
                        add = min(PARAMS['match_bonus'], probs[1] + probs[2])
                        take_n = min(add, probs[1])
                        probs[1] -= take_n
                        probs[2] -= (add - take_n)
                        probs[0] += add
                if g.late:
                    probs = [0.0, probs[0], probs[1] + probs[2]]
                x = rng.random()
                if x < probs[0]:
                    c.add_review('good', m, g)
                elif x < probs[0] + probs[1]:
                    c.add_review('normal', m, g)
                else:
                    c.add_review('bad', m, g)
                stats['paid_customers'] += 1
            stats['revenue'] += g.bill + g.drinks
            stats['drinks'] += g.drinks
            stats['drink_cost'] += g.drink_cost if hasattr(g, 'drink_cost') else 0.0

        # ---------------- 事件循环
        runner_idx = 0
        while ev:
            tnow, _, kind, obj = heapq.heappop(ev)
            if kind == 'arr':
                g = obj
                if free_tables > 0:
                    seat(tnow, g)
                else:
                    door.append(g)
                    push(tnow + P['door_wait'], 'door_to', g)
            elif kind == 'door_to':
                g = obj
                if g.seated is None and not g.left:
                    g.left = True
                    stats['door_left'] += g.size
            elif kind == 'ordered':
                g = obj
                g.order_t = tnow
                c.choose_order(g, menu_key, menu, season_w, season_p, available, rng)
                if not g.reserved_order:
                    g.left = True
                    stats['no_order_left'] += g.size
                    leave_table(tnow, g)
                    continue
                for did, person in g.reserved_order:
                    reserve(did)
                g.hard = max(data.dishes[d]['tier'] for d, _ in g.reserved_order)
                Pt = P['patience']
                g.patience = Pt[g.hard] + P['patience_per_extra'] * (g.size - 1)
                if g.kind == 'reservation':
                    g.patience += 30
                push(tnow + g.patience + P['patience_grace'], 'impatient', g)
                make_tasks(tnow, g)
                dispatch(tnow)
            elif kind == 'begin':
                task = obj
                if task.state == 'cancel':
                    task.stove['busy'] = None
                    dispatch(tnow)
                    continue
                task.state = 'cooking'
                consume(task)
                task.T = tnow + cook_time(task.dish)
                seq[0] += 1
                heapq.heappush(takeouts, (task.T, seq[0], task))   # 同时到点按先后序号，不用 id()，保证逐位复现
                push(task.T, 'wake', None)
                dispatch(tnow)
            elif kind == 'auto_done':
                task = obj
                task.stove['busy'] = None
                stats['auto_plates'] += 1
                d = data.dishes[task.dish]
                q = 'perfect' if d['tier'] < 3 else 'good'
                self.dish_done(tnow, task, q, req_serves, enqueue_task, reserve, available, push)
                dispatch(tnow)
            elif kind == 'tk_done':
                task, q = obj
                task.stove['busy'] = None
                stats['manual_plates'] += 1
                if c.day >= P['auto_count_from_day']:
                    d = data.dishes[task.dish]
                    if (d['tier'] < 3 and q == 'perfect') or (d['tier'] == 3 and q in ('good', 'immortal')):
                        c.manual_good[d['base']] += 1
                if q == 'burnt':
                    stats['burnt'] += 1
                self.dish_done(tnow, task, q, req_serves, enqueue_task, reserve, available, push)
                dispatch(tnow)
            elif kind == 'wake':
                player_try(tnow)
                dispatch(tnow)
            elif kind == 'served':
                g = obj
                if g.left:
                    dispatch(tnow)
                    continue
                g.served = tnow
                stats['wait_sum'] += tnow - g.order_t
                stats['wait_n'] += 1
                if tnow > g.order_t + g.patience + 1e-9:
                    g.late = True
                    stats['late_groups'] += 1
                    stats['late_persons'] += g.size
                for did, q in g.dishes:
                    d = data.dishes[did]
                    if d['novel']:
                        c.novel_count[d['base']] += 1
                push(tnow + P['dine'][g.hard], 'dine_end', g)
                dispatch(tnow)
            elif kind == 'impatient':
                g = obj
                if g.served is None and not g.left:
                    g.left = True
                    stats['impatient_left'] += g.size
                    for task_list in (kitchen, starts):
                        for task in task_list:
                            if task.group is g and task.state == 'queued':
                                task.state = 'cancel'
                                unreserve(task.dish)
                    try:
                        req_serves.remove(g)
                    except ValueError:
                        pass
                    leave_table(tnow, g)
            elif kind == 'dine_end':
                g = obj
                if runner_idx < len(runner_times) and tnow >= runner_times[runner_idx]:
                    g.runner = 1
                    runner_idx += 1
                finish_group(tnow, g)
                leave_table(tnow, g)
        self.groups = groups
        return stats

    def dish_done(self, tnow, task, q, req_serves, enqueue_task, reserve, available, push):
        c = self.c
        g = task.group
        stats = c.day_stats
        if task.hidden_bad and q != 'burnt':
            stats['bad_found_at_takeout'] += 1
            q = 'burnt'
        if q == 'burnt':
            # 作废重做：再扣一份料
            if g.left:
                return
            if available(task.dish):
                reserve(task.dish)
                nt = Task(task.dish, g, task.auto, task.person)
                enqueue_task(tnow, nt)
            else:
                g.tasks_cancel += 1
                self._maybe_serve(tnow, g, req_serves)
            return
        if g.left:
            return
        g.dishes.append((task.dish, q))
        g.tasks_done += 1
        self._maybe_serve(tnow, g, req_serves)

    def _maybe_serve(self, tnow, g, req_serves):
        if g.tasks_done + g.tasks_cancel >= g.tasks_total and g.served is None and not g.left:
            if g.tasks_done == 0:
                return
            # 按实际做出的菜结账
            data = self.c.data
            g.bill = sum(data.dishes[d]['price'] * self.c.season_p.get(d, 1.0) for d, _ in g.dishes)
            req_serves.append(g)


# ------------------------------------------------------------------ 整局（多天）
class Campaign:
    def __init__(self, data, prices, rng, banquet='accept', force_good=None, skill=None, price_scale=1.0):
        self.data = data
        self.rng = rng
        self.prices = scale_prices(prices, price_scale)
        self.banquet_policy = banquet
        self.force_good = force_good
        if skill is not None:
            PARAMS['skill']['delta_mean'] = skill
        P = PARAMS
        self.day = 0
        self.xp = 0
        self.stage = 0
        self.cash = float(P['start_cash'])
        self.tables = 1
        self.expanded = False
        self.expansion_day = None
        self.expansion_ready = None
        self.stove_tiers = [1]
        self.waiters = []            # [{'lvl':1,'hired':day}]
        self.wage_accrued = 0.0
        self.stage_day = {0: 1}
        self.portal_day = None
        self.cola_done = False
        self.xian_day = None
        self.manual_good = defaultdict(int)
        self.novel_count = defaultdict(int)
        self.novel_count_review = {}
        self.tasted = set()
        self.student_good = 0
        self.celeb_good = False
        self.good_rate_prev = 1.0
        self.buff_days = 0
        self.banquet_tomorrow = None
        self.banquet_cooldown = 0
        self.last_banquet_day = -99
        self.stock = defaultdict(float)
        self.hidden = defaultdict(float)
        self.ema_dish = defaultdict(float)    # 选现代食材时用：每位来客点这道菜的份数（指数平滑）
        self.ema_ppc = 1.0                    # 人均盘数
        self.ema_share = {}                   # 各菜点单占比
        self.ema_wine = 0.0
        self.log = []
        self.buildout_day = None
        self.purchases = []
        self.bstats = defaultdict(lambda: defaultdict(float))   # 预算校验
        self.reservations_tomorrow = 0
        self.last_signals = {'door_left': 0, 'stove_wait': 0, 'stove_block': 0, 'impatient': 0}

    # ---- 状态查询
    def is_auto(self, base):
        tier = self.data.dishes[base]['tier']
        return self.manual_good[base] >= PARAMS['auto_cook_counts'][tier]

    def sample_type(self, rng):
        P = PARAMS
        opts = [('worker', P['mix']['worker'])]
        if self.stage >= P['women_from_stage']:
            opts.append(('women', P['mix']['women']))
        if self.day >= P['students_from_day']:
            opts.append(('student', P['mix']['student']))
        tot = sum(w for _, w in opts)
        return choice_w(rng, [(k, w / tot) for k, w in opts])

    def fill_group(self, g, typ, size, rng):
        P = PARAMS
        prof = self.data.profiles
        g.type = typ
        g.celeb = False
        if typ == 'worker':
            n = size or choice_w(rng, P['group_sizes']['worker'])
            g.members = ['worker'] * n
            g.kind = 'I'
        elif typ == 'student':
            n = size or choice_w(rng, P['group_sizes']['student'])
            g.members = ['student'] * n
            g.kind = 'S'
        elif typ == 'women':
            g.members = list(choice_w(rng, P['group_sizes']['women']))
            g.kind = 'S'
        elif typ == 'celebrity':
            n = 1 + rng.randint(*P['celebrity']['companions'])
            g.members = ['celebrity'] * n
            g.kind = 'S'
            g.celeb = True
        else:   # reservation
            n = rng.randint(*P['reservation']['size'])
            g.members = ['celebrity'] * n
            g.kind = 'reservation'
            g.celeb = True
        g.size = len(g.members)
        g.jj = (P['stages']['level'][self.stage] >= P['jiangjiu']['from_level'] and not g.celeb
                and rng.random() < P['jiangjiu']['share'])
        mult = P['jiangjiu']['budget_mult'] if g.jj else 1.0
        if g.celeb:
            g.budget = None
        else:
            g.budget = sum(prof[m]['budget_wen'] for m in g.members) * mult

    def choose_order(self, g, menu_key, menu, season_w, season_p, available, rng):
        data = self.data
        prof = data.profiles
        orders = []
        feasible_all = True
        spend = 0.0
        if g.kind == 'reservation' and available(PARAMS['reservation']['dish']):
            res = PARAMS['reservation']['dish']
            orders.append((res, None))
            # 再配一道主食（和佛跳墙的料分开核对）
            need = defaultdict(float)
            for kk, qq in data.dishes[res]['ings'].items():
                need[kk] += qq

            def avail_r(d):
                return all(self.stock.get(kk, 0) - need[kk] >= qq for kk, qq in data.dishes[d]['ings'].items())
            staples = [d for d in menu if data.dishes[d]['staple'] and avail_r(d)]
            if staples:
                orders.append((max(staples, key=lambda d: data.dishes[d]['sat']), None))
        elif g.kind == 'reservation':
            g.kind = 'S'
            k = max(1, int(0.75 * g.size + 0.5)) + 1
            sig = ('S', tuple(sorted(g.members)), None, k, False, True)
            rec, ok, feasible_all = pick_order(data, rng, menu_key, menu, season_w, season_p, sig, available,
                                              make_combo_ok(data, self.stock))
            if rec is not None:
                for did in rec[1]:
                    orders.append((did, None))
        elif g.kind == 'I':
            tent = defaultdict(float)

            def avail2(did):
                for kk, qq in data.dishes[did]['ings'].items():
                    if self.stock.get(kk, 0) - tent[kk] < qq:
                        return False
                return True
            g.person_dishes = []
            for idx, m in enumerate(g.members):
                b = prof[m]['budget_wen'] * (PARAMS['jiangjiu']['budget_mult'] if g.jj else 1.0)
                sig = ('I', (m,), b, 1, g.jj, False)
                rec, ok, fm = pick_order(data, rng, menu_key, menu, season_w, season_p, sig, avail2,
                                         make_combo_ok(data, self.stock, tent))
                feasible_all &= fm
                if rec is None:
                    g.person_dishes.append(())
                    continue
                g.person_dishes.append(rec[1])
                for did in rec[1]:
                    orders.append((did, idx))
                    for kk, qq in data.dishes[did]['ings'].items():
                        tent[kk] += qq
                spend += rec[2]
        else:
            n = g.size
            k = max(1, int(0.75 * n + 0.5))
            if g.celeb:
                k += 1
            sig = ('S', tuple(sorted(g.members)), g.budget, k, g.jj, g.celeb)
            rec, ok, feasible_all = pick_order(data, rng, menu_key, menu, season_w, season_p, sig, available,
                                              make_combo_ok(data, self.stock))
            if rec is not None:
                for did in rec[1]:
                    orders.append((did, None))
                spend = rec[2]
        g.reserved_order = orders
        # 酒
        g.drinks = 0.0
        g.drink_cost = 0.0
        if orders and self.stage >= 3:
            wines = [w for w in data.wines if self.xp >= w['min_xp']]
            if wines:
                for m in g.members:
                    if m == 'child':
                        continue
                    p = PARAMS['drinks']['celebrity'] if g.celeb else (PARAMS['drinks']['jiangjiu'] if g.jj else 0.0)
                    if p and rng.random() < p and self.stock.get('__wine', 0) >= 1:
                        w = rng.choice(wines)
                        if g.budget is not None and spend + g.drinks + w['direct_sale_price'] / 100.0 > g.budget:
                            continue
                        self.stock['__wine'] -= 1
                        self.used['__wine'] += 1
                        g.drinks += w['direct_sale_price'] / 100.0
                        g.drink_cost += w['base_unit_cost'] / 100.0
        # 预算校验记录
        if g.type in ('worker', 'women', 'student'):
            b = self.bstats[(STAGE_NAMES[self.stage], g.type)]
            b['groups'] += 1
            b['feasible'] += 1 if feasible_all else 0
            b['spend'] += spend
            b['budget'] += g.budget if g.budget else 0.0

    def add_review(self, r, m, g):
        s = self.day_stats
        if self.force_good is not None:
            x = self.rng.random()
            r = 'good' if x < self.force_good else ('normal' if x < self.force_good + (1 - self.force_good) * 0.75 else 'bad')
        s[r] += 1
        s['xp'] += PARAMS['xp'][r]
        if r == 'good' and m == 'student':
            self.student_good += 1
        if r == 'good' and g.celeb:
            self.celeb_good = True

    def try_chase(self, tnow, waiter_busy):
        win = PARAMS['runners']['catch_window']
        for i, b in enumerate(waiter_busy):
            if b <= tnow + win:
                waiter_busy[i] = max(b, tnow) + PARAMS['actions']['chase']
                return True
        return False

    # ---- 价格
    def price_table(self, n):
        return self.prices['table'].get(n)

    def price_stove(self, n):
        return self.prices['stove'].get(n)

    # ---- 一天
    def run_day(self):
        P = PARAMS
        rng = self.rng
        self.day += 1
        d = self.day
        st = stage_of(self.xp)
        if st != self.stage:
            for s in range(self.stage + 1, st + 1):
                self.stage_day.setdefault(s, d)
            self.stage = st
        if self.stage >= 2 and self.portal_day is None:
            self.portal_day = d + 1
        if self.stage >= 3 and self.xian_day is None:
            self.xian_day = d + P['xian_delay_days']
        if self.expansion_ready is not None and d >= self.expansion_ready:
            self.expanded = True
        self.xian_active = self.xian_day is not None and d >= self.xian_day
        self.day_stats = defaultdict(float)
        self.used = defaultdict(float)
        s = self.day_stats
        s['day'] = d
        s['stage'] = self.stage
        cash0 = self.cash

        # ---- 名流家宴日
        if self.banquet_tomorrow is not None:
            lvl = self.banquet_tomorrow
            self.banquet_tomorrow = None
            self.run_banquet(lvl)
            self.accrue_wages()
            self.overnight()
            self.end_of_day(business=False)
            s['net'] = self.cash - cash0
            s['cash'] = self.cash
            self.log.append(dict(s))
            return

        # ---- 早上：添置
        self.tables_open = self.tables_effective()
        self.buy_equipment()
        self.tables_open = self.tables_effective()
        # ---- 今日菜单与采购
        self.plan_menu()
        self.buy_ingredients()
        # ---- 营业
        self.planned_visitors = self.visitors_today()
        self.celebrity_today = (self.stage >= P['celebrity']['from_stage'] and self.student_good >= P['celebrity']['student_good']
                                and rng.random() < P['celebrity']['daily'])
        self.reservations_today = self.reservations_tomorrow
        self.reservations_tomorrow = 0
        self.stock_avail = self.stock          # 同一个 dict：点单时直接扣
        sim = DaySim(self, rng)
        sim.run()
        # ---- 晚上
        self.post_business()
        self.accrue_wages()
        self.overnight()
        self.end_of_day(business=True)
        s['net'] = self.cash - cash0
        s['cash'] = self.cash
        self.log.append(dict(s))

    def tables_effective(self):
        return self.tables + (2 if self.expanded else 0)

    def visitors_today(self):
        P = PARAMS
        cap = P['stages']['cap'][self.stage]
        f = P['reputation']['base'] + P['reputation']['slope'] * self.good_rate_prev
        v = cap * f
        if self.buff_days > 0:
            v = min(cap, v * P['banquet']['buff_mult'])
            self.buff_days -= 1
        return int(v)

    def season(self):
        return ((self.day - 1) // PARAMS['seasons']['days']) % 4   # 0 春 1 夏 2 秋 3 冬

    def plan_menu(self):
        data = self.data
        P = PARAMS
        se = self.season()
        tiers = set()
        for t in self.stove_tiers:
            tiers |= set(range(1, t + 1))
        portal = self.portal_day is not None and self.day >= self.portal_day
        # 选今天的现代食材
        self.modern_today = None
        if portal:
            opts = []
            for m in data.modern:
                ing = data.ing[m]
                if self.xp < ing['min_xp']:
                    continue
                opts.append(m)
            if 'cola' in opts and not self.cola_done:
                self.modern_today = 'cola'
            elif opts:
                best, bv = None, -1
                for m in opts:
                    v = 0.0
                    for d in data.dishes.values():
                        if m in d['modern'] and self.dish_unlocked(d, assume_modern=m) and d['stove'] in tiers:
                            v += max(self.ema_dish[d['id']], P['buy']['new_dish_prior']) * (d['price'] - d['cost'])
                    v *= 1.0 + 0.3 * self.rng.random()
                    if v > bv:
                        best, bv = m, v
                self.modern_today = best
            if self.modern_today == 'cola':
                self.cola_done = True
        menu = []
        for d in data.dishes.values():
            if not self.dish_unlocked(d, assume_modern=self.modern_today):
                continue
            if d['stove'] not in tiers:
                continue
            if d['modern'] and self.modern_today not in d['modern']:
                continue
            if d['id'] == P['reservation']['dish']:
                continue       # 佛跳墙只接预约
            if 'crab' in d['ings'] and se != 2:
                continue
            menu.append(d['id'])
        menu.sort()
        self.today_menu = menu
        self.season_w, self.season_p = {}, {}
        S = P['seasons']
        self.season_w[S['cold_noodle']] = S['boost'] if se == 1 else S['off']
        self.season_p[S['cold_noodle']] = S['price_mult'] if se == 1 else 1.0
        self.season_w[S['crystal']] = S['boost'] if se == 3 else S['off']
        self.season_p[S['crystal']] = S['price_mult'] if se == 3 else 1.0
        self.today_menu_key = (tuple(menu), se)
        # 新菜试味（一次性，送 3 份小份）
        for did in menu:
            d = data.dishes[did]
            if d['novel'] and d['base'] not in self.tasted:
                self.tasted.add(d['base'])
                self.cash -= P['novel']['tasting_portions'] * d['cost']
                self.day_stats['tasting_cost'] += P['novel']['tasting_portions'] * d['cost']

    def dish_unlocked(self, d, assume_modern=None):
        if self.xp < d['xp']:
            return False
        for f in d['flags']:
            if f == 'portal_first_upgrade':
                if self.portal_day is None or self.day < self.portal_day:
                    return False
            elif f == 'first_cola_import':
                if not self.cola_done:
                    return False
        return True

    def expected_customers(self):
        P = PARAMS
        cap = P['stages']['cap'][self.stage]
        f = P['reputation']['base'] + P['reputation']['slope'] * self.good_rate_prev
        return cap * f

    def buy_ingredients(self):
        """按预测用量采购：预计盘数 = 预计来客 × 人均盘数（平滑）；按各菜点单占比分到每道菜，
        加 25% 余量、每道菜至少 2 份；扣掉库存后下单。"""
        data = self.data
        P = PARAMS
        B = P['buy']
        rng = self.rng
        cust = self.expected_customers()
        plates = cust * self.ema_ppc
        menu = self.today_menu
        shares = {}
        default = 1.0 / max(1, len(menu))
        for did in menu:
            shares[did] = self.ema_share.get(did, default)
        tot = sum(shares.values()) or 1.0
        need = defaultdict(float)
        for did in menu:
            n_d = max(B['min_per_dish'], plates * shares[did] / tot * (1 + B['buffer']))
            for k, q in data.dishes[did]['ings'].items():
                need[k] += n_d * q
        for _ in range(self.reservations_tomorrow_count()):
            for k, q in data.dishes[P['reservation']['dish']]['ings'].items():
                need[k] += q
        fh_supply = rng.randint(*P['fish_head_daily'])
        inv_cap = P['stages']['inventory'][self.stage]
        plan = {}
        for k, qty in need.items():
            want = math.ceil(qty) - int(self.stock.get(k, 0))
            if want <= 0:
                continue
            ing = data.ing[k]
            if ing['category'] == 'modern':
                if k != self.modern_today:
                    continue
                want = min(want, data.portal_cap(self.stage) - int(self.stock.get(k, 0)))
            if k == 'fish_head':
                want = min(want, fh_supply)
            if want > 0:
                plan[k] = want

        def is_main(k):
            return k in data.ing and data.ing[k]['category'] not in ('modern', 'wine', 'seasoning')
        main_total = sum(v for k, v in self.stock.items() if is_main(k))
        add_total = sum(v for k, v in plan.items() if is_main(k))
        self.day_stats['inv_wanted'] = main_total + add_total
        if main_total + add_total > inv_cap and add_total > 0:
            scale = max(0.0, (inv_cap - main_total) / add_total)
            for k in list(plan):
                if is_main(k):
                    plan[k] = int(plan[k] * scale)
            self.day_stats['inventory_capped'] += 1
        bargain = {}
        for v in set(VENDOR.values()):
            bargain[v] = (1.0 - B['bargain_cut']) if rng.random() < B['bargain_p'] else 1.0
        spent = 0.0
        auto_inspect = any(w['lvl'] >= 3 for w in self.waiters)
        self.hidden_bad_rate = P['auto_inspect_miss'] if auto_inspect else 0.0
        for k, q in plan.items():
            if q <= 0:
                continue
            ing = data.ing[k]
            base = ing['base_unit_cost']
            mult = 1.0
            bad = ing['bad_rate_normal']
            if ing['category'] in BULK_CATS:
                for th, m in B['bulk']:
                    if q >= th:
                        mult = m
                        bad += B['bulk_bad']
                        break
            if ing['source'] == 'market':
                mult *= bargain.get(VENDOR.get(k, 'x'), 1.0)
            mult = max(B['floor'], mult)
            unit = math.ceil(base * mult) / 100.0
            spent += unit * q
            n_bad = sum(1 for _ in range(q) if rng.random() < bad) if bad > 0 else 0
            good = q - n_bad
            if auto_inspect and n_bad:
                missed = sum(1 for _ in range(n_bad) if rng.random() < P['auto_inspect_miss'])
                self.hidden[k] += missed
                self.stock[k] += good + missed
                self.day_stats['bad_discarded'] += n_bad - missed
            else:
                self.stock[k] += good
                self.day_stats['bad_discarded'] += n_bad
        if self.stage >= 3:
            want_w = math.ceil(self.ema_wine * cust * (1 + B['buffer']) + 2) - int(self.stock.get('__wine', 0))
            if want_w > 0:
                wines = [w for w in data.wines if self.xp >= w['min_xp']]
                if wines:
                    avg = sum(w['base_unit_cost'] for w in wines) / len(wines) / 100.0
                    spent += avg * want_w
                    self.stock['__wine'] += want_w
        self.hidden_bad_share = {k: (self.hidden[k] / self.stock[k]) if self.stock.get(k, 0) > 0 else 0.0 for k in self.hidden}
        self.cash -= spent
        self.day_stats['food_spend'] += spent

    def reservations_tomorrow_pending(self):
        return False

    def reservations_tomorrow_count(self):
        return self.reservations_tomorrow

    def post_business(self):
        s = self.day_stats
        data = self.data
        # 调料钱（开灶时累计）
        self.cash -= s['seas_cost']
        self.day_stats['food_spend'] += s['seas_cost']
        self.cash += s['revenue']
        self.xp += s['xp']
        tot = s['good'] + s['normal'] + s['bad']
        self.good_rate_prev = (s['good'] / tot) if tot else self.good_rate_prev
        # 更新点单预测：人均盘数、各菜占比（指数平滑）
        cust = max(1.0, s['arrived'])
        a = PARAMS['buy']['ema']
        total_plates = sum(self.dish_orders.values())
        if total_plates > 0:
            self.ema_ppc = a * (total_plates / cust) + (1 - a) * self.ema_ppc
            for did in self.today_menu:
                sh = self.dish_orders.get(did, 0.0) / total_plates
                old_sh = self.ema_share.get(did)
                self.ema_share[did] = sh if old_sh is None else a * sh + (1 - a) * old_sh
        for did in self.today_menu:
            rate = self.dish_orders.get(did, 0.0) / cust
            self.ema_dish[did] = a * rate + (1 - a) * self.ema_dish[did] if self.ema_dish[did] > 0 else rate
        wine_rate = self.used.get('__wine', 0) / cust
        self.ema_wine = a * wine_rate + (1 - a) * self.ema_wine
        aw = (s['auto_wait'] / s['auto_started']) if s['auto_started'] else 0.0
        self.last_signals = {'door_left': s['door_left'], 'stove_wait': aw, 'stove_block': s['stove_block'],
                             'impatient': s['impatient_left']}
        # 名流家宴邀请
        P = PARAMS
        if self.banquet_policy == 'accept' and self.stage >= P['banquet']['from_stage'] and self.celeb_good:
            if self.banquet_cooldown <= 0 and self.rng.random() < P['banquet']['daily']:
                self.banquet_tomorrow = P['stages']['level'][self.stage]
        if self.banquet_cooldown > 0:
            self.banquet_cooldown -= 1
        # 明天的预约
        if self.stage >= P['reservation']['from_stage'] and 3 in self.stove_tiers_set():
            self.reservations_tomorrow = self.rng.randint(*P['reservation']['per_day'])

    def stove_tiers_set(self):
        return set(self.stove_tiers)

    def run_banquet(self, lvl):
        P = PARAMS
        Bq = P['banquet']
        rng = self.rng
        cfg = None
        for L in self.data.J['rules']['banquet']['levels']:
            if L['level'] == lvl:
                cfg = L
        brng = getattr(self, 'brng', None) or rng            # 经费档用单独的随机数流，不打乱营业的随机序列
        diff = brng.choice(list(Bq['difficulty_bonus_mult']))
        mult = Bq['difficulty_bonus_mult'][diff]
        met = rng.random() < Bq['p_host_met']
        score = min(100.0, rng.gauss(Bq['score_mean'], Bq['score_sd'])) if met else Bq['capped_score']
        fee, bonus, xp = cfg['base_fee'] / 100.0, cfg['bonus'] / 100.0 * mult, cfg['xp']
        if score >= 90:
            money, gx, rating = fee + 2 * bonus, math.floor(xp * 1.25), '十分满意'
        elif score >= 70:
            money, gx, rating = fee + bonus, xp, '满意'
        elif score >= 50:
            money, gx, rating = fee, math.floor(xp * 0.5), '尚可'
        else:
            money, gx, rating = fee * 0.5, math.floor(xp * 0.25), '不满意'
        self.cash += money
        self.xp += gx
        s = self.day_stats
        s['banquet'] = 1
        s['banquet_money'] = money
        s['banquet_difficulty'] = diff
        s['xp'] = gx
        s['revenue'] = money
        if score >= 70:
            self.buff_days = Bq['buff_days']
        self.banquet_cooldown = Bq['cooldown_business_days']

    def accrue_wages(self):
        for w in self.waiters:
            self.wage_accrued += PARAMS['wages'][w['lvl']] / 10.0
        if self.day % 10 == 0:
            self.cash -= self.wage_accrued
            self.day_stats['wages_paid'] += self.wage_accrued
            self.wage_accrued = 0.0
        self.day_stats['wages_accrued'] = sum(PARAMS['wages'][w['lvl']] / 10.0 for w in self.waiters)

    def overnight(self):
        data = self.data
        rng = self.rng
        for k in list(self.stock):
            if k == '__wine' or self.stock[k] <= 0:
                continue
            r = data.ing[k]['overnight_bad_rate']
            if r > 0:
                n = int(self.stock[k])
                lost = sum(1 for _ in range(n) if rng.random() < r)
                self.stock[k] -= lost
                self.day_stats['overnight_lost'] += lost

    def end_of_day(self, business):
        if self.tables_effective() >= 12 and len(self.stove_tiers) >= 12 and self.buildout_day is None:
            self.buildout_day = self.day

    # ---- 添置
    def buy_equipment(self):
        """贪心添置：先保证必需（第一名小二、二级的第一口中等灶、四级的第一口高等灶），再买"卡住"的
        产能（座位不够就加桌或扩建；后厨排队就加灶）。座位卡住但钱不够时攒钱，不买别的；其余情况在留出
        当天食材钱和临近的工钱后，按 桌子 → 灶台 → 灶台升级 → 小二升级 的顺序补齐。"""
        P = PARAMS
        pr = self.prices
        st = self.stage
        S = P['stages']
        sig = self.last_signals
        est_food = max(30.0, self.last_food * (self.expected_customers() / max(1.0, self.last_customers)))
        dtp = (10 - self.day % 10) % 10          # 距发工钱还有几天（0 = 今天晚上发）
        daily_wage = sum(P['wages'][w['lvl']] / 10.0 for w in self.waiters)
        wage_soon = (self.wage_accrued + daily_wage * (dtp + 1)) if dtp <= 3 else 0.0
        reserve = est_food + wage_soon + P['policy']['reserve_extra']
        cushion = P['policy']['fill_cushion']

        def can(cost, extra=0.0):
            return cost is not None and self.cash - cost >= reserve + extra

        def buy(what, cost):
            self.cash -= cost
            self.purchases.append((self.day, what, cost))
            self.day_stats['equip_spend'] += cost

        for _ in range(60):
            n_tab = self.tables_effective()
            n_st = len(self.stove_tiers)
            # 必需：小二
            if self.day >= P['first_waiter_day'] and not self.waiters:
                self.waiters.append({'lvl': 1, 'hired': self.day})
                self.purchases.append((self.day, 'waiter1', 0))
                continue
            if self.waiters and len(self.waiters) < S['waiters'][st] and n_tab > P['actions']['tables_per_waiter'] * len(self.waiters):
                if can(P['waiter_fee']):
                    buy('waiter', P['waiter_fee'])
                    self.waiters.append({'lvl': 1, 'hired': self.day})
                    continue
            # 必需：灶台等级
            if st >= 3 and max(self.stove_tiers) < 2:
                if can(pr['upgrade'][2]):
                    self.upgrade_stove(2, buy)
                    continue
            if st >= 5 and max(self.stove_tiers) < 3:
                cost = pr['upgrade'][3] + (0 if 2 in self.stove_tiers else pr['upgrade'][2])
                if can(cost):
                    if 2 not in self.stove_tiers:
                        self.upgrade_stove(2, buy)
                    self.upgrade_stove(3, buy)
                    continue
            # 卡住的产能：座位
            nxt = self.next_table()
            seats_bind = sig['door_left'] > 0 or sig['impatient'] > 0
            if seats_bind and nxt:
                if can(nxt[1]):
                    self.do_table(nxt[0], nxt[1], buy)
                    continue
                break      # 攒钱买桌/扩建
            # 卡住的产能：后厨
            if (sig['stove_wait'] > 1.0 or sig.get('stove_block', 0) > 5) and n_st < S['stoves'][st]:
                cost = self.price_stove(n_st + 1)
                if can(cost):
                    buy('stove%d' % (n_st + 1), cost)
                    self.stove_tiers.append(1)
                    continue
                break
            # 一楼 4 张桌已满、座位卡住：从二级起就为扩建攒钱（三级才能扩建）
            if (seats_bind and not self.expanded and self.expansion_ready is None
                    and self.tables_effective() >= 4 and st >= 3):
                break
            # 补齐
            if nxt and can(nxt[1], cushion):
                self.do_table(nxt[0], nxt[1], buy)
                continue
            if nxt:
                break      # 还有桌子没买齐：先攒钱买桌
            if n_st < S['stoves'][st]:
                cost = self.price_stove(n_st + 1)
                if can(cost, cushion):
                    buy('stove%d' % (n_st + 1), cost)
                    self.stove_tiers.append(1)
                    continue
                break
            if st >= 3:
                need_mid = math.ceil(P['policy']['medium_share'] * len(self.stove_tiers))
                if sum(1 for t in self.stove_tiers if t >= 2) < need_mid:
                    if can(pr['upgrade'][2], cushion):
                        self.upgrade_stove(2, buy)
                        continue
                    break
            if st >= 5:
                need_hi = math.ceil(P['policy']['high_share'] * len(self.stove_tiers))
                if sum(1 for t in self.stove_tiers if t >= 3) < need_hi:
                    cost = pr['upgrade'][3] + (0 if any(t == 2 for t in self.stove_tiers) else pr['upgrade'][2])
                    if can(cost, cushion):
                        if not any(t == 2 for t in self.stove_tiers):
                            self.upgrade_stove(2, buy)
                        self.upgrade_stove(3, buy)
                        continue
                    break
            done = False
            for w in self.waiters:
                if w['lvl'] == 1 and st >= 3 and self.day - w['hired'] >= P['waiter_level2_days']:
                    fee = P['waiter_upgrade_fee'][2]
                    if can(fee, cushion):
                        buy('waiter_lv2', fee)
                        w['lvl'] = 2
                        done = True
                    break
                if w['lvl'] == 2 and st >= 5:
                    fee = P['waiter_upgrade_fee'][3]
                    if can(fee, cushion):
                        buy('waiter_lv3', fee)
                        w['lvl'] = 3
                        done = True
                    break
            if done:
                continue
            break

    def next_table(self):
        st = self.stage
        S = PARAMS['stages']
        pr = self.prices
        n = self.tables_effective()
        if n >= S['tables'][st]:
            return None
        if n < 4:
            return ('table%d' % (n + 1), pr['table'][n + 1])
        if n == 4 and not self.expanded:
            if self.expansion_ready is not None:
                return None          # 已付款，明天开放
            return ('expansion', pr['expansion'])
        if n >= 6:
            return ('table%d' % (n + 1), pr['table'].get(n + 1))
        return None

    def do_table(self, what, cost, buy):
        buy(what, cost)
        if what == 'expansion':
            self.expansion_day = self.day
            self.expansion_ready = self.day + 1
        else:
            self.tables += 1

    def upgrade_stove(self, to, buy):
        pr = self.prices
        for i, t in enumerate(self.stove_tiers):
            if t == to - 1:
                self.stove_tiers[i] = to
                buy('upgrade%d' % to, pr['upgrade'][to])
                return True
        return False

    def run(self, horizon=None):
        horizon = horizon or PARAMS['horizon']
        self.last_food = 60.0
        self.last_customers = 12.0
        self.dish_orders = defaultdict(float)
        while self.day < horizon:
            self.dish_orders = defaultdict(float)
            self._patch_orders()
            self.run_day()
            s = self.log[-1]
            if not s.get('banquet'):
                self.last_food = max(30.0, s.get('food_spend', 60.0))
                self.last_customers = max(1.0, s.get('arrived', 12.0))
            if self.stage == 6 and self.buildout_day is not None and self.day >= max(self.stage_day.get(6, 0), self.buildout_day) + 10:
                break
        return self

    def _patch_orders(self):
        # 在点单时累计每道菜份数（给预测用）
        camp = self
        orig = Campaign.choose_order

        def wrapped(g, *a, **k):
            orig(camp, g, *a, **k)
            for did, _ in (g.reserved_order or []):
                camp.dish_orders[did] += 1
        self.choose_order = wrapped


def scale_prices(prices, s):
    if s == 1.0:
        return prices
    def r10(x):
        return int(round(x * s / 10.0)) * 10
    def r50(x):
        return int(round(x * s / 50.0)) * 50
    return {
        'table': {k: r10(v) for k, v in prices['table'].items()},
        'expansion': r50(prices['expansion']),
        'stove': {k: r10(v) for k, v in prices['stove'].items()},
        'upgrade': {k: r10(v) for k, v in prices['upgrade'].items()},
    }


# ------------------------------------------------------------------ 蒙特卡洛与汇总
def pct(xs, p):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    i = (len(xs) - 1) * p
    lo, hi = int(math.floor(i)), int(math.ceil(i))
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def monte_carlo(data, prices, runs=200, seed=1, banquet='accept', force_good=None, skill=None, price_scale=1.0,
                horizon=None, keep_logs=False):
    res = []
    skill0 = PARAMS['skill']['delta_mean']
    for r in range(runs):
        rng = random.Random(seed * 100003 + r)
        c = Campaign(data, prices, rng, banquet, force_good, skill, price_scale)
        c.brng = random.Random((seed * 100003 + r) * 7 + 3)
        c.run(horizon)
        res.append(c)
        PARAMS['skill']['delta_mean'] = skill0
    return summarize(res, keep_logs)


def summarize(camps, keep_logs=False):
    P_BUSINESS = float(PARAMS['business_seconds'])
    out = {'runs': len(camps)}
    for s in range(1, 7):
        xs = [c.stage_day.get(s) for c in camps]
        out['stage_%d' % s] = (pct(xs, 0.5), pct(xs, 0.1), pct(xs, 0.9), sum(1 for x in xs if x is None))
    xs = [c.expansion_day for c in camps]
    out['expansion'] = (pct(xs, 0.5), pct(xs, 0.1), pct(xs, 0.9), sum(1 for x in xs if x is None))
    xs = [c.buildout_day for c in camps]
    out['buildout'] = (pct(xs, 0.5), pct(xs, 0.1), pct(xs, 0.9), sum(1 for x in xs if x is None))
    exp_before_4 = [1 if (c.expansion_day is not None and c.stage_day.get(5) is not None and c.expansion_day < c.stage_day[5]) else 0 for c in camps]
    out['expansion_before_lv4_share'] = sum(exp_before_4) / len(camps)
    for d in (10, 20, 30):
        xs = [c.log[d - 1]['cash'] for c in camps if len(c.log) >= d]
        out['cash_day%d' % d] = (pct(xs, 0.5), pct(xs, 0.1), pct(xs, 0.9))
    # 每级收支（营业日）
    per = {}
    for s in range(7):
        rows = [row for c in camps for row in c.log if row['stage'] == s and not row.get('banquet')]
        if not rows:
            continue
        def m(key):
            return statistics.mean(r.get(key, 0.0) for r in rows)
        paid = m('paid_customers')
        per[STAGE_NAMES[s]] = {
            'days': len(rows) / len(camps),
            'arrived': m('arrived'), 'paid': paid, 'door_left': m('door_left'), 'impatient': m('impatient_left'),
            'revenue': m('revenue'), 'food': m('food_spend'), 'wages': m('wages_accrued'),
            'net_operating': m('revenue') - m('food_spend') - m('wages_accrued'),
            'good_rate': statistics.mean((r['good'] / (r['good'] + r['normal'] + r['bad'])) if (r['good'] + r['normal'] + r['bad']) else 0 for r in rows),
            'xp': m('xp'), 'spend_per_paid': (m('revenue') / paid) if paid else 0.0,
            'late_groups': m('late_groups'), 'burnt': m('burnt'),
        }
        def tot(key):
            return sum(r.get(key, 0.0) for r in rows)
        plates = tot('manual_plates') + tot('auto_plates')
        per[STAGE_NAMES[s]].update({
            'plates_per_day': plates / len(rows),
            'manual_share': tot('manual_plates') / plates if plates else 0.0,
            'takeover_share': tot('takeover_plates') / plates if plates else 0.0,
            'player_util': tot('player_busy_s') / (P_BUSINESS * len(rows)),
            'auto_wait': tot('auto_wait') / tot('auto_started') if tot('auto_started') else 0.0,
            'wait_avg': tot('wait_sum') / tot('wait_n') if tot('wait_n') else 0.0,
            'late_share': tot('late_groups') / tot('groups_paid') if tot('groups_paid') else 0.0,
            'impatient_share': tot('impatient_left') / tot('arrived') if tot('arrived') else 0.0,
        })
    out['per_stage'] = per
    # 五级稳定期：买满后
    rev5 = []
    for c in camps:
        rows = [row for row in c.log if row['stage'] == 6 and not row.get('banquet')]
        if c.buildout_day:
            rows = [r for r in rows if r['day'] >= c.buildout_day] or rows
        if rows:
            rev5.append(statistics.mean(r['revenue'] for r in rows))
    out['rev5_daily'] = (pct(rev5, 0.5), pct(rev5, 0.1), pct(rev5, 0.9))
    full = 4 * PARAMS['wages'][3]
    out['wage_share_full_staff'] = full / (out['rev5_daily'][0] * 10) if out['rev5_daily'][0] else None
    # 家宴
    out['banquets_before_lv5'] = statistics.mean(sum(1 for r in c.log if r.get('banquet') and r['day'] < (c.stage_day.get(6) or 999)) for c in camps)
    # 预算校验
    agg = defaultdict(lambda: defaultdict(float))
    for c in camps:
        for k, v in c.bstats.items():
            for kk, vv in v.items():
                agg[k][kk] += vv
    out['budget'] = {'%s|%s' % k: {'groups': v['groups'], 'feasible_share': v['feasible'] / v['groups'] if v['groups'] else None,
                                  'spend_share': v['spend'] / v['budget'] if v['budget'] else None}
                     for k, v in sorted(agg.items())}
    # 购置时间线（中位数）
    tl = defaultdict(list)
    for c in camps:
        seen = {}
        for day, what, cost in c.purchases:
            if what not in seen:
                seen[what] = day
        for what, day in seen.items():
            tl[what].append(day)
    out['timeline'] = {w: (pct(v, 0.5), len(v) / len(camps)) for w, v in tl.items()}
    # 校验
    out['checks'] = validation(camps)
    if keep_logs:
        out['_camps'] = camps
    return out


def validation(camps):
    P = PARAMS
    chk = {}
    rows = [(row, c) for c in camps for row in c.log if not row.get('banquet')]
    # 来客 ≈ 上限 × 口碑系数（到店人数不超过上限）
    over = sum(1 for r, c in rows if r.get('arrived_ordinary', 0) > P['stages']['cap'][r['stage']])
    chk['arrivals_over_cap_days'] = over
    neg = sum(1 for c in camps for k, v in c.stock.items() if v < -1e-6)
    chk['negative_stock_items'] = neg
    chk['min_cash'] = min(r['cash'] for r, c in rows)
    ratio = []
    for r, c in rows:
        cap = P['stages']['cap'][r['stage']]
        ratio.append(r.get('arrived_ordinary', 0) / cap)
    chk['arrived_over_cap_mean'] = statistics.mean(ratio)
    chk['inventory_capped_days_share'] = sum(1 for r, c in rows if r.get('inventory_capped')) / len(rows)
    return chk


# ------------------------------------------------------------------ 标定
def calibrate(data, runs=100, seed=7):
    """返回标定用的代价函数 cost_of(prices) -> (cost, result)：中位节奏贴近设计目标（二级 6、三级 8、
    四级 11、五级 14）、12 桌 12 灶在 16–20 天买满、扩建尽量在四级前。网格和结果见 results.md。"""
    cur = PARAMS['price_sets']['current']
    target = {'stage_3': 6, 'stage_4': 8, 'stage_5': 11, 'stage_6': 14}

    def cost_of(pr):
        r = monte_carlo(data, pr, runs=runs, seed=seed)
        c = 0.0
        for k, v in target.items():
            m = r[k][0] if r[k][0] is not None else 40
            c += (m - v) ** 2
        b = r['buildout'][0] if r['buildout'][0] is not None else 60
        if b > 20:
            c += (b - 20) ** 2
        elif b < 16:
            c += (16 - b) ** 2 * 0.5
        c += 4.0 * (1 - r['expansion_before_lv4_share']) ** 2
        return c, r

    return cost_of


def contest_estimate(camps, rival=838, seed=7, stage=6, cap=96, profit_base=1500, emperor_dish='high', celebrities=True):
    """把五级买满后每个营业日的结果套进正店比拼公式，估算单局得分和夺冠概率。
    另扣比拼当天两名逃单客被追回（按差评）、集中到店让 3 人没准时；营业收益按收入的六成（菜单成本约四成）。
    特殊分：皇帝点高等菜、玩家亲手做，出仙味 80 分，否则 20 分（满意率 95%）；名流一位必来、第二位 60%，
    每位亲手做高等菜出仙味 30 分，否则 10 分。出仙味的概率按玩家的出炉反应时间算。"""
    S = PARAMS['skill']
    dmin, dmean = S['delta_min'], S['delta_mean']
    p_xian = (1 - S['early']) * (1 - math.exp(-(0.7 - dmin) / max(1e-9, dmean - dmin)))
    rng = random.Random(seed)

    def rnd(x):
        return math.floor(x + 0.5)
    scores, base, no_xian = [], [], []
    for c in camps:
        rows = [row for row in c.log if row['stage'] == stage and not row.get('banquet')]
        if stage == 6 and c.buildout_day:
            rows = [x for x in rows if x['day'] >= c.buildout_day] or rows
        for row in rows:
            G, N, B = row['good'], row['normal'], row['bad']
            P = G + N + B
            if P <= 0:
                continue
            T = max(0, P - row.get('late_persons', 0) - 3)
            G2, B2 = max(0, G - 2), B + 2
            parts = (rnd(400 * (6 * G2 + 4 * N + 2 * B2) / (6 * P)), rnd(min(180, 180 * P / cap)), rnd(180 * T / P),
                     rnd(100 * min(1, max(0, row['revenue'] * 0.6) / profit_base)))
            if emperor_dish == 'high':
                sp = 80 if rng.random() < p_xian else (20 if rng.random() < 0.95 else 0)
            else:       # 只有中等菜：亲手做出完美 35 分（3 秒内出炉即完美）
                sp = 35 if rng.random() < (1 - S['early']) else (20 if rng.random() < 0.95 else 0)
            if celebrities:
                for _ in range(2 if rng.random() < 0.6 else 1):
                    sp += 30 if rng.random() < p_xian else (10 if rng.random() < 0.95 else 0)
            scores.append(sum(parts) + sp)
            base.append(parts)
            no_xian.append(sum(parts) + 20 + (10 if celebrities else 0))
    n = len(scores)
    ss = sorted(scores)
    return {'days': n, 'p_xian': p_xian, 'median': statistics.median(scores), 'p10': ss[int(0.1 * n)], 'p90': ss[int(0.9 * n)],
            'quantiles': {q: ss[min(n - 1, int(q / 100 * n))] for q in (0.5, 1, 2, 3.5, 5, 10, 19.5, 25, 50, 75, 90)},
            'win_share': sum(1 for x in scores if x >= rival) / n, 'second_share': sum(1 for x in scores if x >= 788) / n,
            'parts_median': [statistics.median(p[i] for p in base) for i in range(4)],
            'no_xian_median': statistics.median(no_xian), 'no_xian_win_share': sum(1 for x in no_xian if x >= rival) / n}


# ------------------------------------------------------------------ 家宴经费三档的标定
BANQUET_HOSTS = ['sushi', 'suzhe', 'ouyangxiu', 'meiyaochen', 'zenggong', 'chenghao']


def banquet_budget_report(J, n=20000, seed=2026):
    """按规则随机生成"能拿满菜单分"的家宴菜单，算实际材料成本（普通档，验货丢掉的坏料也要买），
    列出成本分布、三档经费下放得进经费的比例，以及三种玩家（随便选／看提示调整／精打细算）的平均净收入。"""
    ING = {i['id']: i for i in J['ingredients']}
    BQ = J['rules']['banquet']
    LEVELS = {L['level']: L for L in BQ['levels']}
    mult = BQ['budget_difficulty']['bonus_mult']
    wine = BQ['budget_difficulty']['ouyangxiu_wine_allowance_per_drinker'] / 100.0
    rec = J['recipes']

    def real_cost(r):
        c = sum(q * ING[k]['base_unit_cost'] / 100.0 / (1 - (ING[k].get('bad_rate_normal') or 0.0))
                for k, q in r['ingredients'].items())
        return c + sum(q * ING[k]['base_unit_cost'] / 100.0 for k, q in r['seasonings'].items())
    cost = {r['id']: real_cost(r) for r in rec}
    modern = {r['id']: [k for k in r['ingredients'] if ING[k]['category'] == 'modern'] for r in rec}
    rng = random.Random(seed)

    def eligible(L):
        return [r for r in rec if r['unlock']['shop_level'] <= L and r['required_stove_tier'] <= LEVELS[L]['stove_tier']]

    def parts(total, m):
        cuts = sorted(rng.sample(range(1, total), m - 1)) if m > 1 else []
        out, prev = [], 0
        for c in cuts + [total]:
            out.append(c - prev)
            prev = c
        return out

    def sample(L, host):
        lv = LEVELS[L]
        k, N, B = lv['distinct_recipes'], lv['plates'], lv['batch_plates']
        pool = eligible(L)
        dishes = rng.sample(pool, k)
        if host == 'zenggong':
            zc = [r for r in pool if ({'mild', 'savory'} & set(r['taste_tags'])) and 'spicy' not in r['taste_tags']]
            if rng.choice(zc) not in dishes:
                return None
        rng.shuffle(dishes)
        m1 = rng.randint(1, min(B[0], k - 2))
        m2 = rng.randint(1, min(B[1], k - m1 - 1))
        m3 = k - m1 - m2
        if m3 < 1 or m3 > B[2]:
            return None
        groups = [dishes[:m1], dishes[m1:m1 + m2], dishes[m1 + m2:]]
        if not any(r['is_staple'] for r in groups[2]):
            return None
        plates = []
        for g, b in zip(groups, B):
            plates += list(zip(g, parts(b, len(g))))
        kinds, units = set(), 0
        for r, pn in plates:
            if 'fish_head' in r['ingredients'] and pn > 4:
                return None
            for mm in modern[r['id']]:
                kinds.add(mm)
                units += pn
        if len(kinds) > lv['modern_types'] or units > lv['modern_units']:
            return None
        staple = sum(pn for r, pn in plates if r['is_staple'])
        tags = {t for r, pn in plates for t in r['taste_tags']}
        sat = sum(pn * r['satiety'] for r, pn in plates)
        if staple < 0.25 * N or len(tags) < 3 or sat < lv['guests'] * 100:
            return None
        if host == 'sushi' and not any(r['is_novel_recipe'] for r, pn in plates):
            return None
        if host == 'meiyaochen' and not any(r['difficulty'] == 1 for r, pn in plates):
            return None
        if host == 'chenghao':
            if not any('mild' in r['taste_tags'] for r, pn in plates):
                return None
            if sum(pn for r, pn in plates if 'spicy' not in r['taste_tags']) < 0.75 * N:
                return None
        if host == 'ouyangxiu' and sum(pn for r, pn in plates if 'wine' in r['taste_tags']) > 0.5 * N:
            return None
        c = sum(pn * cost[r['id']] for r, pn in plates)
        if host == 'ouyangxiu':
            c += (lv['guests'] // 2) * wine
        return c, sum(pn for r, pn in plates if r['difficulty'] == 3) / N

    def menus(L, count, host=None):
        out = []
        while len(out) < count:
            x = sample(L, host)
            if x:
                out.append(x)
        return out

    def q(xs, p):
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(p * len(xs)))]
    report = {}
    print('  家宴菜单实际成本（能拿满菜单分，普通档，含丢坏料；每级 %d 份）与三档经费' % n)
    for L in sorted(LEVELS):
        lv = LEVELS[L]
        cs = [c for c, h in menus(L, n)]
        bud = {k: v / 100.0 for k, v in lv['budget_by_difficulty'].items()}
        fit = {k: sum(1 for c in cs if c <= v) / len(cs) for k, v in bud.items()}
        print('   %d 级：最低 %.0f  P25 %.0f  中位 %.0f  P75 %.0f  最高 %.0f；经费 %s；放得进经费的菜单 %s' % (
            L, min(cs), q(cs, .25), q(cs, .5), q(cs, .75), max(cs), bud,
            {k: '%.0f%%' % (100 * v) for k, v in fit.items()}))
        pools = {h: menus(L, max(500, n // 8), h) for h in BANQUET_HOSTS}
        base, bonus = lv['base_fee'] / 100.0, lv['bonus'] / 100.0
        rows = {}
        for d, B0 in bud.items():
            for strat in ('随便选', '看提示调整', '精打细算'):
                money, over_n = [], 0
                for i in range(6000):
                    h = BANQUET_HOSTS[i % 6]
                    B = B0 + ((lv['guests'] // 2) * wine if h == 'ouyangxiu' else 0)
                    pool = pools[h]

                    def score(m):
                        over = max(0.0, m[0] - B)
                        sc = 35 * (0.95 * (1 - m[1]) + 0.85 * m[1]) + 60 + 5 * max(0.0, 1 - over / (0.2 * B))
                        if h == 'suzhe' and over > 0:
                            sc = min(sc, 69)
                        return sc, over
                    if strat == '随便选':
                        m = rng.choice(pool)
                    else:
                        cand = [rng.choice(pool) for _ in range(5 if strat == '看提示调整' else 20)]
                        ok = [x for x in cand if x[0] <= B]
                        if ok:
                            m = ok[0] if strat == '看提示调整' else max(ok, key=lambda x: score(x)[0])
                        else:
                            m = min(cand)
                    sc, over = score(m)
                    over_n += over > 0
                    if sc >= 50:
                        pay = base + (2 if sc >= 90 else 1 if sc >= 70 else 0) * bonus * mult[d]
                    else:
                        pay = base * 0.5
                    money.append(pay - over)
                rows[(d, strat)] = (statistics.mean(money), over_n / 6000)
        print('      平均净收入（文）／超支场次：' + '；'.join('%s·%s %.0f／%.0f%%' % (d, st, v[0], 100 * v[1])
                                                    for (d, st), v in rows.items()))
        report[L] = {'costs': [min(cs), q(cs, .25), q(cs, .5), q(cs, .75), max(cs)], 'fit': fit,
                     'income': {'%s|%s' % k: v for k, v in rows.items()}}
    return report


def fmt_range(t):
    if t is None or t[0] is None:
        return '—'
    return '%.0f（%.0f–%.0f）' % (t[0], t[1], t[2])


def print_report(r, title):
    print('=' * 70)
    print(title, ' runs=%d' % r['runs'])
    for s in range(1, 7):
        print('  %-4s 首日 中位(P10–P90) = %s  未达=%d' % (STAGE_NAMES[s], fmt_range(r['stage_%d' % s]), r['stage_%d' % s][3]))
    print('  扩建  %s  未扩建=%d   四级前扩建比例 %.0f%%' % (fmt_range(r['expansion']), r['expansion'][3], 100 * r['expansion_before_lv4_share']))
    print('  买满  %s  未买满=%d' % (fmt_range(r['buildout']), r['buildout'][3]))
    for d in (10, 20, 30):
        v = r['cash_day%d' % d]
        if v[0] is not None:
            print('  第%d天现金 %s' % (d, fmt_range(v)))
    print('  五级日营业额 %s；满编工钱占比 %s' % (fmt_range(r['rev5_daily']),
          ('%.0f%%' % (100 * r['wage_share_full_staff'])) if r['wage_share_full_staff'] else '—'))
    print('  四级前参加家宴（场/局）%.1f' % r['banquets_before_lv5'])
    print('  阶段      天数  来客  付款  门口走  等走  收入  食材  工钱  经营净额  好评率  人均')
    for k, v in r['per_stage'].items():
        print('  %-5s %5.1f %5.1f %5.1f %5.1f %5.1f %6.0f %5.0f %5.0f %8.0f %6.0f%% %5.1f' % (
            k, v['days'], v['arrived'], v['paid'], v['door_left'], v['impatient'], v['revenue'], v['food'],
            v['wages'], v['net_operating'], 100 * v['good_rate'], v['spend_per_paid']))
    print('  后厨      盘/天  手做比例  手做盘/分  其中接手  玩家忙碌  自动等灶(秒)  等菜均时(秒)  催单组比  等不及走')
    for k, v in r['per_stage'].items():
        print('  %-5s %6.1f %8.0f%% %9.1f %8.0f%% %8.0f%% %10.1f %12.1f %9.1f%% %8.1f%%' % (
            k, v['plates_per_day'], 100 * v['manual_share'], v['plates_per_day'] * v['manual_share'] / (PARAMS['business_seconds'] / 60.0),
            100 * v['takeover_share'], 100 * v['player_util'], v['auto_wait'],
            v['wait_avg'], 100 * v['late_share'], 100 * v['impatient_share']))
    print('  校验', r['checks'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('json')
    ap.add_argument('--runs', type=int, default=200)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--prices', default='current')
    ap.add_argument('--banquet', default='accept')
    ap.add_argument('--force-good', type=float, default=None)
    ap.add_argument('--skill', type=float, default=None)
    ap.add_argument('--price-scale', type=float, default=1.0)
    ap.add_argument('--inventory', default='proposed', choices=['proposed', 'original'])
    ap.add_argument('--auto-cap', default=None, help='自动做同时最多占几口灶：一个数，或 7 个以逗号分隔的数（一级①…五级）；none＝不限；默认 2')
    ap.add_argument('--player-start', type=float, default=None, help='玩家亲手投料的秒数（默认 1.5）')
    ap.add_argument('--player-takeout', type=float, default=None, help='玩家点出炉的秒数（默认 0.5，不含反应时间）')
    ap.add_argument('--contest', action='store_true', help='另外估算正店比拼的得分和夺冠概率')
    ap.add_argument('--banquet-budget', action='store_true', help='只做家宴经费三档的标定（菜单成本分布、放得进经费的比例、三种玩家的净收入）')
    ap.add_argument('--trial-contest', action='store_true', help='估算八周试玩版的比拼（升三级后比拼，只有中等菜，皇帝一人，按三级上限折算）')
    ap.add_argument('--out', default=None, help='把结果另存为 JSON（默认不存）')
    a = ap.parse_args()
    if a.auto_cap == 'none':
        PARAMS['auto_cap'] = None
    elif a.auto_cap:
        xs = [int(x) for x in a.auto_cap.split(',')]
        PARAMS['auto_cap'] = xs * 7 if len(xs) == 1 else xs
        assert len(PARAMS['auto_cap']) == 7, '--auto-cap 要 1 个或 7 个数，或 none'
    if a.player_start is not None:
        PARAMS['actions']['start'] = a.player_start
    if a.player_takeout is not None:
        PARAMS['actions']['takeout'] = a.player_takeout
    data = Data(a.json)
    if a.banquet_budget:
        banquet_budget_report(data.J)
        return
    if a.inventory == 'original':
        PARAMS['stages']['inventory'] = list(PARAMS['inventory_original'])
    prices = PARAMS['price_sets'][a.prices]
    if prices is None:
        sys.exit('price set %s not calibrated yet' % a.prices)
    t0 = time.time()
    r = monte_carlo(data, prices, a.runs, a.seed, a.banquet, a.force_good, a.skill, a.price_scale, keep_logs=a.contest or a.trial_contest)
    if a.contest or a.trial_contest:
        skill0 = PARAMS['skill']['delta_mean']
        if a.skill is not None:
            PARAMS['skill']['delta_mean'] = a.skill
        if a.contest:
            r['contest'] = contest_estimate(r['_camps'])
        if a.trial_contest:
            r['trial_contest'] = contest_estimate(r['_camps'], rival=0, stage=4, cap=54, profit_base=850, emperor_dish='medium', celebrities=False)
        PARAMS['skill']['delta_mean'] = skill0
    print_report(r, '价格=%s 家宴=%s 好评=%s 手感=%s 价格倍数=%s 自动灶上限=%s' % (a.prices, a.banquet, a.force_good, a.skill,
                                                                          a.price_scale, PARAMS['auto_cap']))
    if a.contest:
        ce = r['contest']
        print('  正店比拼估算：%d 个五级营业日，亲手做高等菜出仙味 %.0f%%；总分中位 %.0f（P10–P90 %d–%d），单局夺冠（≥838）%.1f%%，超过第二名（≥788）%.1f%%'
              % (ce['days'], 100 * ce['p_xian'], ce['median'], ce['p10'], ce['p90'], 100 * ce['win_share'], 100 * ce['second_share']))
        print('    经营四项中位（评价／人数／准时／收益）%s；皇帝那道没出仙味时总分中位 %.0f，夺冠 %.1f%%'
              % ('／'.join('%.0f' % x for x in ce['parts_median']), ce['no_xian_median'], 100 * ce['no_xian_win_share']))
    if a.trial_contest:
        tc = r['trial_contest']
        print('  试玩版比拼估算：%d 个三级营业日；总分中位 %.0f（P10–P90 %d–%d）；分位 %s；经营四项中位 %s'
              % (tc['days'], tc['median'], tc['p10'], tc['p90'], tc['quantiles'], '／'.join('%.0f' % x for x in tc['parts_median'])))
    print('  用时 %.1f 秒' % (time.time() - t0))
    if a.out:
        json.dump({k: v for k, v in r.items() if not k.startswith('_')}, open(a.out, 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1, default=str)


if __name__ == '__main__':
    main()
