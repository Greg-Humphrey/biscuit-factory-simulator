# ==========================================================
# INGREDIENTS ENGINE
# ==========================================================
# This file defines:
# - Ingredient cost per kg
# - Biscuit recipes
# - Monthly demand levels
# - Selling prices
#
# It is a pure data + lookup engine.
#
# It does NOT:
# - Perform validation
# - Run simulation logic
# - Apply scenario effects
#
# Other engines that depend on this:
# - simulation_engine (cost + revenue calculations)
# - decision_engine (biscuit validation)
# ==========================================================


# ----------------------------------------------------------
# INGREDIENT COSTS (per kg)
# ----------------------------------------------------------

ingredients = {
    "flour": 0.75,
    "gluten_free_flour": 3,
    "eggs": 3,
    "sugar": 1.2,
    "icing": 2.3,
    "butter": 10.5,
    "vegetable_oil": 2.2,
    "treacle": 2.6,
    "vegetable_fat": 3.7
}


# ----------------------------------------------------------
# BISCUIT DEFINITIONS
# - recipe quantities are per batch (10,000 biscuits)
# - batch_price is per 10,000 biscuits
# ----------------------------------------------------------

biscuits = {
    "custom_iced": {
        "recipe": {
            "flour": 400,
            "eggs": 80,
            "sugar": 150,
            "icing": 250,
            "butter": 120
        },
        "monthly_demand": 110000,
        "batch_price": 1800
    },

    "shortbread": {
        "recipe": {
            "flour": 500,
            "sugar": 170,
            "butter": 330
        },
        "monthly_demand": 75000,
        "batch_price": 2700
    },

    "gluten_free": {
        "recipe": {
            "gluten_free_flour": 550,
            "eggs": 30,
            "sugar": 200,
            "vegetable_oil": 220
        },
        "monthly_demand": 90000,
        "batch_price": 2300
    },

    "gingerbread": {
        "recipe": {
            "flour": 560,
            "eggs": 40,
            "sugar": 180,
            "treacle": 220
        },
        "monthly_demand": 200000,
        "batch_price": 1000
    },

    "digestive": {
        "recipe": {
            "flour": 680,
            "sugar": 180,
            "vegetable_oil": 140
        },
        "monthly_demand": 220000,
        "batch_price": 900
    },

    "custard_creams": {
        "recipe": {
            "flour": 500,
            "sugar": 180,
            "icing": 200,
            "vegetable_fat": 120
        },
        "monthly_demand": 180000,
        "batch_price": 1100
    },

    "rich_tea": {
        "recipe": {
            "flour": 740,
            "sugar": 160,
            "vegetable_oil": 100
        },
        "monthly_demand": 235000,
        "batch_price": 850
    }
}


# ----------------------------------------------------------
# COST CALCULATIONS
# ----------------------------------------------------------

def calculate_ingredient_cost(biscuit_name):

    total_batch_cost = 0
    recipe = biscuits[biscuit_name]["recipe"]

    for ingredient, qty_in_kg in recipe.items():
        total_batch_cost += qty_in_kg * ingredients[ingredient]

    # Convert batch cost (10,000 biscuits) to cost per biscuit
    return total_batch_cost / 10000


def get_monthly_demand(biscuit_name):
    return biscuits[biscuit_name]["monthly_demand"]


def get_batch_price(biscuit_name):
    # Convert batch price (10,000 biscuits) to price per biscuit
    batch_price = biscuits[biscuit_name]["batch_price"]
    return batch_price / 10000


def get_all_biscuit_names():
    return list(biscuits.keys())
