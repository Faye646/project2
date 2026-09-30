using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json.Linq;

namespace BianHe.Core
{
    public class Ingredient
    {
        public string Id, Name, Category;
        public int UnitCost, MinShopLevel;
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
        public int Xp, VisitorCap, TableCap, StoveCap;
        public long ArrivalIntervalMs;
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
                    UnitCost = (int?)i["base_unit_cost"] ?? 0, MinShopLevel = (int?)i["min_shop_level"] ?? 1,
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
                    ArrivalIntervalMs = (long)((double)s["arrival_interval_seconds"] * 1000),
                });
            return d;
        }

        public StageInfo StageFor(int xp) => Stages.Last(s => xp >= s.Xp);

        public StageInfo NextStage(int xp) => Stages.FirstOrDefault(s => s.Xp > xp);

        public string IngredientName(string id) => Ingredients.TryGetValue(id, out var i) ? i.Name : id;

        public string IngredientList(Recipe r) => string.Join("、", r.Ingredients.Keys.Select(IngredientName));
    }
}
