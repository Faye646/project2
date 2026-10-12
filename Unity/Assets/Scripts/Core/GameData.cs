using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace BianHe.Core
{
    /// <summary>
    /// An ingredient, seasoning, wine or modern food as the market sells it (《玩法与数值》06 采购、验货与库存): its vendor,
    /// its price (and the 优质 grade's, if it has one), how often a portion comes bad (普通 / 优质), how often one left
    /// overnight spoils, and from how much experience it is on sale. Money in 1/100 文.
    /// </summary>
    public class Ingredient
    {
        public string Id, Name, Category, Shelf, Vendor, Source, Condition;
        public int UnitCost, PremiumCost, MinShopLevel, MinXp;
        public double BadRate, BadRatePremium, OvernightBad;

        public bool HasPremium => PremiumCost > 0;
        public bool IsSeasoning => Category == "seasoning";
        public bool IsWine => Category == "wine";
        public bool IsModern => Category == "modern";

        /// <summary>主食材: what counts toward the storeroom's cap (seasonings and wine are kept apart, modern food has its own).</summary>
        public bool IsMain => !IsSeasoning && !IsWine && !IsModern;
    }

    /// <summary>
    /// The market's rules (rules.procurement and rules.service.bargain): 优质 costs half as much again; ten or more of one
    /// 普通 main ingredient at once is a tenth off and twenty or more a fifth (the bottom of such a heap comes bad more
    /// often); a vendor can be asked to come down once a day; no price goes under seven tenths of the list price; a
    /// dish whose main ingredients are all 优质 is liked better; and 自动验货 misses a twentieth of the bad portions.
    /// </summary>
    public class ProcurementRules
    {
        public double PremiumMultiplier = 1.5;
        public readonly SortedDictionary<int, double> Bulk = new();   // at least this many → this much of the price
        public double Floor = 0.7;
        public double BulkBadAdd = 0.05;
        public int BulkBadThreshold = 10;
        public double AutoInspectionMiss = 0.05;
        public double PremiumGoodPp = 10;
        public readonly List<(string line, double discount, double success)> Bargains = new();
    }

    public class Recipe
    {
        public string Id, Name, Description, Temperature;
        public int Difficulty, CookMs, Price, BaseCost, ShopLevel, UnlockXp, Satiety;
        public StoveTier StoveTier;
        public string[] RequiredFlags, TasteTags, SuggestedGroups;
        public Dictionary<string, int> Ingredients = new();
        public Dictionary<string, int> Seasonings = new();   // only the ones the recipe uses (qty > 0)

        /// <summary>Unlocked at this XP with no story flags pending.</summary>
        public bool IsOpen(int xp, ICollection<string> flags) =>
            xp >= UnlockXp && RequiredFlags.All(flags.Contains);
    }

    public class CustomerProfile
    {
        public string Id, Name;
        public int TargetSatiety, BudgetWen;
        public string[] Prefer, Avoid;
    }

    /// <summary>A step of 声望 (一级①, 一级② …) with its daily visitor cap and pace.</summary>
    public class StageInfo
    {
        public string Id, Name;
        public int Xp, VisitorCap, TableCap, StoveCap, InventoryCap;
        public long ArrivalIntervalMs;
    }

    /// <summary>
    /// What the shop floor sells (rules.economy.tables and .expansion; 《玩法与数值》04 桌椅、灶台与扩建): the price of
    /// each table by its number (the first is free), how many fit downstairs, and the 二楼 with 雅间一, which comes with
    /// its own two tables from a given stage and opens the day after it is paid for. Money in 1/100 文.
    /// </summary>
    public class PremisesRules
    {
        public readonly Dictionary<int, int> TablePrice = new();
        public int GroundFloorMax = 4;
        public int ExpansionPrice;
        public string ExpansionMinStage = "3";
        public int[] ExpansionTables = { 5, 6 };
        public int PrivateRoom1 = 6, PrivateRoom2 = 12;   // 雅间一 comes with the 二楼; 雅间二 is the last table
        public int MaxTables = 12;
    }

    /// <summary>
    /// Typed view of 汴河两岸_菜品与家宴数据.json (schema 1.3): recipes, ingredients, customer profiles
    /// and the reputation stages. Money stays in the file's unit, 1/100 文.
    /// </summary>
    public class GameData
    {
        public string SchemaVersion;
        public readonly List<Recipe> Recipes = new();
        public readonly Dictionary<string, Ingredient> Ingredients = new();
        public readonly Dictionary<string, CustomerProfile> Profiles = new();
        public readonly List<StageInfo> Stages = new();
        public readonly PremisesRules Premises = new();
        public readonly ProcurementRules Procurement = new();
        public int StartCash;

        static string[] Strings(JToken t) => t == null ? new string[0] : t.Select(x => (string)x).ToArray();

        public static GameData Parse(string json)
        {
            var root = JObject.Parse(json);
            var d = new GameData { SchemaVersion = (string)root["schema_version"] };
            foreach (var i in root["ingredients"])
            {
                var ing = new Ingredient
                {
                    Id = (string)i["id"], Name = (string)i["name"], Category = (string)i["category"],
                    Shelf = (string)i["display_category"], Vendor = (string)i["vendor"], Source = (string)i["source"],
                    Condition = (string)i["purchase_condition"],
                    UnitCost = (int?)i["base_unit_cost"] ?? 0, MinShopLevel = (int?)i["min_shop_level"] ?? 1,
                    PremiumCost = (bool?)i["premium_available"] == true ? (int?)i["premium_unit_cost"] ?? 0 : 0,
                    MinXp = (int?)i["min_xp"] ?? 0,
                    BadRate = (double?)i["bad_rate_normal"] ?? 0, BadRatePremium = (double?)i["bad_rate_premium"] ?? 0,
                    OvernightBad = (double?)i["overnight_bad_rate"] ?? 0,
                };
                d.Ingredients[ing.Id] = ing;
            }
            foreach (var r in root["recipes"])
            {
                var unlock = r["unlock"];
                var rec = new Recipe
                {
                    Id = (string)r["id"], Name = (string)r["name"], Description = (string)r["description"],
                    Difficulty = (int)r["difficulty"],
                    StoveTier = (StoveTier)(int)r["required_stove_tier"],
                    CookMs = (int)System.Math.Round((double)r["cook_seconds"] * 1000),
                    Price = (int)r["default_price"], BaseCost = (int?)r["base_cost"] ?? 0,
                    Satiety = (int?)r["satiety"] ?? 100, Temperature = (string)r["temperature"],
                    TasteTags = Strings(r["taste_tags"]), SuggestedGroups = Strings(r["suggested_customer_groups"]),
                    ShopLevel = (int)unlock["shop_level"], UnlockXp = (int)unlock["cumulative_xp"],
                    RequiredFlags = Strings(unlock["required_flags"]),
                };
                foreach (var p in (JObject)r["ingredients"]) rec.Ingredients[p.Key] = (int)p.Value;
                if (r["seasonings"] is JObject seas)
                    foreach (var p in seas)
                        if ((int)p.Value > 0) rec.Seasonings[p.Key] = (int)p.Value;
                d.Recipes.Add(rec);
            }

            var rules = root["rules"];
            var names = rules["service"]["customer_types"].ToDictionary(t => (string)t["id"], t => (string)t["name"]);
            foreach (var p in (JObject)root["customer_profiles"])
            {
                if (p.Value["budget_wen"]?.Type != JTokenType.Integer) continue;   // 名流 has no budget
                d.Profiles[p.Key] = new CustomerProfile
                {
                    Id = p.Key, Name = names.TryGetValue(p.Key, out var n) ? n : p.Key,
                    TargetSatiety = (int)p.Value["target_satiety"], BudgetWen = (int)p.Value["budget_wen"],
                    Prefer = Strings(p.Value["prefer"]), Avoid = Strings(p.Value["avoid"]),
                };
            }
            var eco = rules["economy"];
            d.StartCash = (int?)eco["start_cash"] ?? 30000;
            foreach (var s in eco["stages"])
                d.Stages.Add(new StageInfo
                {
                    Id = (string)s["stage"], Name = (string)s["name"], Xp = (int)s["xp"],
                    VisitorCap = (int)s["visitor_cap"], TableCap = (int)s["table_cap"], StoveCap = (int)s["stove_cap"],
                    InventoryCap = (int?)s["inventory_cap"] ?? 60,
                    ArrivalIntervalMs = (long)((double)s["arrival_interval_seconds"] * 1000),
                });

            var pr = d.Premises;
            var tables = eco["tables"];
            foreach (var p in (JObject)tables["price_by_number"]) pr.TablePrice[int.Parse(p.Key)] = (int)p.Value;
            pr.GroundFloorMax = (int?)tables["ground_floor_max"] ?? 4;
            var exp = eco["expansion"];
            pr.ExpansionPrice = (int)exp["price"];
            pr.ExpansionMinStage = (string)exp["min_stage"];
            pr.ExpansionTables = exp["adds_tables"].Select(x => (int)x).ToArray();
            pr.MaxTables = d.Stages.Max(s => s.TableCap);

            var proc = rules["procurement"];
            var pc = d.Procurement;
            pc.PremiumMultiplier = (double?)proc["premium_multiplier"] ?? 1.5;
            foreach (var p in (JObject)proc["bulk_discount_thresholds"]) pc.Bulk[int.Parse(p.Key)] = (double)p.Value;
            pc.Floor = (double?)proc["floor_multiplier"] ?? 0.7;
            pc.BulkBadAdd = (double?)proc["bulk_bad_rate_addition"] ?? 0.05;
            pc.BulkBadThreshold = (int?)proc["bulk_bad_rate_threshold"] ?? 10;
            pc.AutoInspectionMiss = (double?)proc["inspection"]?["auto_inspection"]?["miss_rate"] ?? 0.05;
            pc.PremiumGoodPp = (double?)rules["service"]["review_modifiers_percentage_points"]?["premium_all_main_ingredients"] ?? 10;
            foreach (var o in rules["service"]["bargain"]["options"])
                pc.Bargains.Add(((string)o["line"], (double)o["discount"], (double)o["success"]));
            return d;
        }

        public StageInfo StageFor(int xp) => Stages.Last(s => xp >= s.Xp);

        /// <summary>Where a stage stands in the order of 声望 (一级① is 0), -1 if there is none by that id.</summary>
        public int StageIndex(string id) => Stages.FindIndex(s => s.Id == id);

        public StageInfo NextStage(int xp) => Stages.FirstOrDefault(s => s.Xp > xp);

        public string IngredientName(string id) => Ingredients.TryGetValue(id, out var i) ? i.Name : id;

        public string IngredientList(Recipe r) => string.Join("、", r.Ingredients.Keys.Select(IngredientName));
    }
}
