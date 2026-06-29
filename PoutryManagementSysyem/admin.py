from django.contrib import admin

from .models import (
    EggProduction,
    EggPrice,
    EggSale,
    Expense,
    FeedConsumption,
    FeedMix,
    FeedMixDetail,
    Flock,
    Income,
    InventoryItem,
    PoultryHouse,
    ProfitSnapshot,
    Purchase,
)


admin.site.site_header = 'Poultry Business Management System'
admin.site.site_title = 'Poultry Management'
admin.site.index_title = 'Farm Operations'


@admin.register(PoultryHouse)
class PoultryHouseAdmin(admin.ModelAdmin):
    list_display = ('house_name', 'capacity', 'bird_type', 'status')
    list_filter = ('bird_type', 'status')
    search_fields = ('house_name',)


@admin.register(Flock)
class FlockAdmin(admin.ModelAdmin):
    list_display = ('breed', 'house', 'purchase_date', 'number_of_birds', 'current_birds', 'balance', 'remarks_status', 'total_cost')
    list_filter = ('remarks', 'breed', 'house')
    search_fields = ('breed', 'house__house_name')
    date_hierarchy = 'purchase_date'


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ('item_name', 'category', 'current_stock', 'reorder_level', 'needs_reorder')
    list_filter = ('category',)
    search_fields = ('item_name', 'category')


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ('purchase_date', 'item_name', 'category', 'quantity', 'unit_price', 'reorder_level', 'total_amount')
    list_filter = ('category', 'purchase_date')
    search_fields = ('item_name', 'category')
    date_hierarchy = 'purchase_date'
    readonly_fields = ('total_amount',)


class FeedMixDetailInline(admin.TabularInline):
    model = FeedMixDetail
    extra = 1
    readonly_fields = ('total_price',)


@admin.register(FeedMix)
class FeedMixAdmin(admin.ModelAdmin):
    list_display = ('mix_name', 'mixing_date', 'total_cost', 'price_per_kg')
    list_filter = ('mixing_date',)
    search_fields = ('mix_name',)
    date_hierarchy = 'mixing_date'
    inlines = [FeedMixDetailInline]


@admin.register(FeedMixDetail)
class FeedMixDetailAdmin(admin.ModelAdmin):
    list_display = ('feed_mix', 'purchase', 'inventory_item', 'quantity', 'unit_price', 'total_price')
    list_filter = ('feed_mix', 'inventory_item')
    search_fields = ('feed_mix__mix_name', 'purchase__item_name', 'inventory_item__item_name')
    readonly_fields = ('total_price',)


@admin.register(FeedConsumption)
class FeedConsumptionAdmin(admin.ModelAdmin):
    list_display = ('consumption_date', 'flock', 'feed_mix', 'quantity', 'issued_by')
    list_filter = ('consumption_date', 'flock')
    search_fields = ('flock__breed', 'issued_by', 'remarks')
    date_hierarchy = 'consumption_date'


@admin.register(EggProduction)
class EggProductionAdmin(admin.ModelAdmin):
    list_display = ('production_date', 'flock', 'eggs_collected', 'broken_eggs', 'dirty_eggs', 'good_eggs')
    list_filter = ('production_date', 'flock')
    search_fields = ('flock__breed',)
    date_hierarchy = 'production_date'
    readonly_fields = ('good_eggs',)


@admin.register(EggPrice)
class EggPriceAdmin(admin.ModelAdmin):
    list_display = ('sale_type', 'rate', 'effective_date', 'is_active')
    list_filter = ('sale_type', 'is_active', 'effective_date')
    date_hierarchy = 'effective_date'


@admin.register(EggSale)
class EggSaleAdmin(admin.ModelAdmin):
    list_display = ('sale_date', 'egg_production', 'egg_price', 'sale_type', 'quantity', 'rate', 'total_amount', 'payment_method')
    list_filter = ('sale_type', 'payment_method', 'sale_date')
    date_hierarchy = 'sale_date'
    readonly_fields = ('total_amount',)


@admin.register(Income)
class IncomeAdmin(admin.ModelAdmin):
    list_display = ('income_date', 'income_type', 'amount')
    list_filter = ('income_type', 'income_date')
    search_fields = ('income_type', 'description')
    date_hierarchy = 'income_date'


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('expense_date', 'category', 'amount', 'payment_method')
    list_filter = ('category', 'payment_method', 'expense_date')
    search_fields = ('category', 'description')
    date_hierarchy = 'expense_date'


@admin.register(ProfitSnapshot)
class ProfitSnapshotAdmin(admin.ModelAdmin):
    list_display = ('period_type', 'period_start', 'period_end', 'total_income', 'total_expenses', 'net_profit')
    list_filter = ('period_type', 'period_start')
    date_hierarchy = 'period_start'
    readonly_fields = ('net_profit',)
