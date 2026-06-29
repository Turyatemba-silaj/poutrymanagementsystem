from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class PoultryHouse(TimeStampedModel):
    LAYER = 'Layer'
    BROILER = 'Broiler'
    OTHER = 'Other'
    BIRD_TYPE_CHOICES = [
        (LAYER, 'Layer'),
        (BROILER, 'Broiler'),
        (OTHER, 'Other'),
    ]

    ACTIVE = 'Full capacity'
    MAINTENANCE = 'Half capacity'
    INACTIVE = 'Empty'
    STATUS_CHOICES = [
        (ACTIVE, 'Full capacity'),
        (MAINTENANCE, 'Half capacity'),
        (INACTIVE, 'Empty'),
    ]

    house_name = models.CharField(max_length=100, unique=True)
    capacity = models.PositiveIntegerField()
    bird_type = models.CharField(max_length=20, choices=BIRD_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=ACTIVE)

    class Meta:
        ordering = ['house_name']

    def __str__(self):
        return self.house_name


class Flock(TimeStampedModel):
    detail_properties = ['balance']

    ISA_BROWN = 'ISA Brown'
    LOHMANN_BROWN = 'Lohmann Brown'
    RHODE_ISLAND_RED = 'Rhode Island Red'
    KUROILER = 'Kuroiler'
    COBB_500 = 'Cobb 500'
    ROSS_308 = 'Ross 308'
    SASSO = 'Sasso'
    LOCAL = 'Local'
    OTHER = 'Other'
    BREED_CHOICES = [
        (ISA_BROWN, 'ISA Brown'),
        (LOHMANN_BROWN, 'Lohmann Brown'),
        (RHODE_ISLAND_RED, 'Rhode Island Red'),
        (KUROILER, 'Kuroiler'),
        (COBB_500, 'Cobb 500'),
        (ROSS_308, 'Ross 308'),
        (SASSO, 'Sasso'),
        (LOCAL, 'Local'),
        (OTHER, 'Other'),
    ]

    DIED = 'Died'
    SICK = 'Sick'
    AVAILABLE = 'Available'
    REMARK_CHOICES = [
        (AVAILABLE, 'Available'),
        (DIED, 'Died'),
        (SICK, 'Sick'),
    ]

    house = models.ForeignKey(PoultryHouse, on_delete=models.PROTECT, related_name='flocks')
    breed = models.CharField(max_length=100, choices=BREED_CHOICES)
    purchase_date = models.DateField(default=timezone.localdate)
    number_of_birds = models.PositiveIntegerField()
    cost_per_bird = models.DecimalField(max_digits=12, decimal_places=2)
    current_birds = models.PositiveIntegerField()
    remarks = models.CharField(max_length=20, choices=REMARK_CHOICES, default=AVAILABLE)

    class Meta:
        ordering = ['-purchase_date', 'breed']

    @property
    def total_cost(self):
        return self.number_of_birds * self.cost_per_bird

    @property
    def balance(self):
        return self.number_of_birds - self.current_birds

    @property
    def remarks_status(self):
        if self.balance > 0:
            return f'{self.balance} {self.remarks}'
        return self.AVAILABLE

    def save(self, *args, **kwargs):
        if self.current_birds is None:
            self.current_birds = self.number_of_birds
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.breed} - {self.house}'


class InventoryItem(TimeStampedModel):
    item_name = models.CharField(max_length=120, unique=True)
    category = models.CharField(max_length=80)
    unit = models.CharField(max_length=30, default='kg')
    current_stock = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reorder_level = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ['item_name']

    @property
    def needs_reorder(self):
        return self.current_stock <= self.reorder_level

    def adjust_stock(self, quantity):
        self.current_stock = (self.current_stock or Decimal('0')) + Decimal(quantity)
        self.save(update_fields=['current_stock', 'updated_at'])

    def __str__(self):
        return f'{self.item_name} ({self.current_stock} {self.unit})'


class Purchase(TimeStampedModel):
    FEED = 'Feed'
    FEEDS = 'Feeds'
    FEED_INGREDIENTS = 'Feed Ingredients'
    SUPPLEMENTS = 'Supplements'
    MEDICINE = 'Medicine'
    STATIONERY = 'Stationery'
    FUEL = 'Fuel'
    EQUIPMENT = 'Equipment'
    CHEMICALS = 'Chemicals'
    OTHER = 'Other'
    CATEGORY_CHOICES = [
        (FEED, 'Feed'),
        (FEEDS, 'Feeds'),
        (FEED_INGREDIENTS, 'Feed Ingredients'),
        (SUPPLEMENTS, 'Supplements'),
        (MEDICINE, 'Medicine'),
        (STATIONERY, 'Stationery'),
        (FUEL, 'Fuel'),
        (EQUIPMENT, 'Equipment'),
        (CHEMICALS, 'Chemicals'),
        (OTHER, 'Other'),
    ]
    ITEM_NAME_CHOICES = [
        ('Layer Mash', 'Layer Mash'),
        ('Grower Mash', 'Grower Mash'),
        ('Starter Feed', 'Starter Feed'),
        ('Broiler Starter', 'Broiler Starter'),
        ('Broiler Grower', 'Broiler Grower'),
        ('Broiler Finisher', 'Broiler Finisher'),
        ('Chick Starter', 'Chick Starter'),
        ('Chick Mash', 'Chick Mash'),
        ('Layer Pellets', 'Layer Pellets'),
        ('Grower Pellets', 'Grower Pellets'),
        ('Broiler Pellets', 'Broiler Pellets'),
        ('Maize Bran', 'Maize Bran'),
        ('Whole Maize', 'Whole Maize'),
        ('Maize Germ', 'Maize Germ'),
        ('Wheat Bran', 'Wheat Bran'),
        ('Wheat Pollard', 'Wheat Pollard'),
        ('Rice Bran', 'Rice Bran'),
        ('Broken Rice', 'Broken Rice'),
        ('Sorghum', 'Sorghum'),
        ('Millet', 'Millet'),
        ('Cassava Flour', 'Cassava Flour'),
        ('Soya', 'Soya'),
        ('Soybean Meal', 'Soybean Meal'),
        ('Cotton Cake', 'Cotton Cake'),
        ('Groundnut Cake', 'Groundnut Cake'),
        ('Sunflower Cake', 'Sunflower Cake'),
        ('Sesame Cake', 'Sesame Cake'),
        ('Palm Kernel Cake', 'Palm Kernel Cake'),
        ('Concentrate', 'Concentrate'),
        ('Fish Meal', 'Fish Meal'),
        ('Blood Meal', 'Blood Meal'),
        ('Bone Meal', 'Bone Meal'),
        ('Meat And Bone Meal', 'Meat And Bone Meal'),
        ('Shell', 'Shell'),
        ('Oyster Shell', 'Oyster Shell'),
        ('Limestone', 'Limestone'),
        ('DCP', 'DCP'),
        ('Salt', 'Salt'),
        ('Vitamin Premix', 'Vitamin Premix'),
        ('Mineral Premix', 'Mineral Premix'),
        ('Amino Acid Premix', 'Amino Acid Premix'),
        ('Lysine', 'Lysine'),
        ('Methionine', 'Methionine'),
        ('Toxin Binder', 'Toxin Binder'),
        ('Molasses', 'Molasses'),
        ('Newcastle Vaccine', 'Newcastle Vaccine'),
        ('Medicine', 'Medicine'),
        ('Disinfectant', 'Disinfectant'),
        ('Receipt Book', 'Receipt Book'),
        ('Paper', 'Paper'),
        ('Pen', 'Pen'),
        ('File', 'File'),
        ('Fuel', 'Fuel'),
        ('Feeder', 'Feeder'),
        ('Drinker', 'Drinker'),
        ('Egg Tray', 'Egg Tray'),
        ('Crate', 'Crate'),
        ('Other', 'Other'),
    ]
    ITEM_CATEGORY_MAP = {
        'Layer Mash': FEEDS,
        'Grower Mash': FEEDS,
        'Starter Feed': FEEDS,
        'Broiler Starter': FEEDS,
        'Broiler Grower': FEEDS,
        'Broiler Finisher': FEEDS,
        'Chick Starter': FEEDS,
        'Chick Mash': FEEDS,
        'Layer Pellets': FEEDS,
        'Grower Pellets': FEEDS,
        'Broiler Pellets': FEEDS,
        'Maize Bran': FEED_INGREDIENTS,
        'Whole Maize': FEED_INGREDIENTS,
        'Maize Germ': FEED_INGREDIENTS,
        'Wheat Bran': FEED_INGREDIENTS,
        'Wheat Pollard': FEED_INGREDIENTS,
        'Rice Bran': FEED_INGREDIENTS,
        'Broken Rice': FEED_INGREDIENTS,
        'Sorghum': FEED_INGREDIENTS,
        'Millet': FEED_INGREDIENTS,
        'Cassava Flour': FEED_INGREDIENTS,
        'Soya': FEED_INGREDIENTS,
        'Soybean Meal': FEED_INGREDIENTS,
        'Cotton Cake': FEED_INGREDIENTS,
        'Groundnut Cake': FEED_INGREDIENTS,
        'Sunflower Cake': FEED_INGREDIENTS,
        'Sesame Cake': FEED_INGREDIENTS,
        'Palm Kernel Cake': FEED_INGREDIENTS,
        'Concentrate': FEED_INGREDIENTS,
        'Fish Meal': FEED_INGREDIENTS,
        'Blood Meal': FEED_INGREDIENTS,
        'Bone Meal': FEED_INGREDIENTS,
        'Meat And Bone Meal': FEED_INGREDIENTS,
        'Shell': SUPPLEMENTS,
        'Oyster Shell': SUPPLEMENTS,
        'Limestone': SUPPLEMENTS,
        'DCP': SUPPLEMENTS,
        'Salt': SUPPLEMENTS,
        'Vitamin Premix': SUPPLEMENTS,
        'Mineral Premix': SUPPLEMENTS,
        'Amino Acid Premix': SUPPLEMENTS,
        'Lysine': SUPPLEMENTS,
        'Methionine': SUPPLEMENTS,
        'Toxin Binder': SUPPLEMENTS,
        'Molasses': SUPPLEMENTS,
        'Newcastle Vaccine': MEDICINE,
        'Medicine': MEDICINE,
        'Disinfectant': CHEMICALS,
        'Receipt Book': STATIONERY,
        'Paper': STATIONERY,
        'Pen': STATIONERY,
        'File': STATIONERY,
        'Fuel': FUEL,
        'Feeder': EQUIPMENT,
        'Drinker': EQUIPMENT,
        'Egg Tray': EQUIPMENT,
        'Crate': EQUIPMENT,
        'Other': OTHER,
    }
    UNIT_RULES = [
        (('feed', 'feeds', 'mash', 'bran', 'maize', 'soya', 'concentrate', 'premix', 'starter', 'grower', 'layer', 'supplements', 'lysine', 'methionine', 'dcp', 'limestone', 'shell', 'salt', 'molasses'), 'kg'),
        (('stationery', 'stationary', 'book', 'paper', 'pen', 'file', 'marker', 'receipt'), 'pc'),
        (('medicine', 'vaccine', 'drug', 'treatment'), 'bottle'),
        (('fuel', 'water', 'disinfectant', 'sanitizer', 'chemical'), 'litre'),
        (('equipment', 'tool', 'tray', 'crate', 'feeder', 'drinker'), 'pc'),
    ]

    purchase_date = models.DateField(default=timezone.localdate)
    inventory_item = models.ForeignKey(
        InventoryItem,
        on_delete=models.PROTECT,
        related_name='purchases',
        null=True,
        blank=True,
    )
    item_name = models.CharField(max_length=120, choices=ITEM_NAME_CHOICES)
    category = models.CharField(max_length=80, choices=CATEGORY_CHOICES)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit = models.CharField(max_length=30, default='kg')
    reorder_level = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    stock_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, editable=False, default=0)

    class Meta:
        ordering = ['-purchase_date', 'item_name']

    def infer_unit(self):
        description = f'{self.category} {self.item_name}'.lower()
        for keywords, unit in self.UNIT_RULES:
            if any(keyword in description for keyword in keywords):
                return unit
        return 'pc'

    def _sync_inventory_item(self):
        self.category = self.ITEM_CATEGORY_MAP.get(self.item_name, self.category)
        self.unit = self.infer_unit()

        item, created = InventoryItem.objects.get_or_create(
            item_name=self.item_name,
            defaults={
                'category': self.category,
                'unit': self.unit,
                'current_stock': Decimal('0'),
                'reorder_level': self.reorder_level,
            },
        )
        if not created:
            changed_fields = []
            if item.category != self.category:
                item.category = self.category
                changed_fields.append('category')
            if item.unit != self.unit:
                item.unit = self.unit
                changed_fields.append('unit')
            if item.reorder_level != self.reorder_level:
                item.reorder_level = self.reorder_level
                changed_fields.append('reorder_level')
            if changed_fields:
                changed_fields.append('updated_at')
                item.save(update_fields=changed_fields)
        self.inventory_item = item

    def _stock_delta(self):
        if not self.pk or not self.inventory_item_id:
            return self.quantity
        previous = Purchase.objects.filter(pk=self.pk).values('inventory_item_id', 'quantity').first()
        if not previous:
            return self.quantity
        if previous['inventory_item_id'] != self.inventory_item_id:
            old_item = InventoryItem.objects.filter(pk=previous['inventory_item_id']).first()
            if old_item:
                old_item.adjust_stock(-previous['quantity'])
            return self.quantity
        return self.quantity - previous['quantity']

    def _stock_balance_delta(self):
        if not self.pk:
            self.stock_balance = self.quantity
            return
        previous = Purchase.objects.filter(pk=self.pk).values('quantity', 'stock_balance').first()
        if not previous:
            self.stock_balance = self.quantity
            return
        self.stock_balance = previous['stock_balance'] + self.quantity - previous['quantity']

    def adjust_stock_balance(self, quantity):
        self.stock_balance = (self.stock_balance or Decimal('0')) + Decimal(quantity)
        Purchase.objects.filter(pk=self.pk).update(stock_balance=self.stock_balance, updated_at=timezone.now())

    def save(self, *args, **kwargs):
        self._sync_inventory_item()
        delta = self._stock_delta()
        self._stock_balance_delta()
        self.total_amount = self.quantity * self.unit_price
        super().save(*args, **kwargs)
        if self.inventory_item_id and delta:
            self.inventory_item.adjust_stock(delta)

    def delete(self, *args, **kwargs):
        item = self.inventory_item
        quantity = self.quantity
        super().delete(*args, **kwargs)
        if item:
            item.adjust_stock(-quantity)

    def __str__(self):
        return f'{self.item_name} - {self.purchase_date}'


class FeedMix(TimeStampedModel):
    detail_properties = ['total_quantity', 'total_unit_price', 'total_cost', 'stock']

    LAYER_FORMULA = 'Layer Formula'
    GROWER_FORMULA = 'Grower Formula'
    PROTEIN_MIX = 'Protein Mix'
    EMPTY_FORMULA = 'Empty Formula'
    CHICK_STARTER = 'Chick Starter'
    BROILER_STARTER = 'Broiler Starter'
    BROILER_GROWER = 'Broiler Grower'
    BROILER_FINISHER = 'Broiler Finisher'
    LAYER_MASH = 'Layer Mash'
    GROWER_MASH = 'Grower Mash'
    DEVELOPER_MASH = 'Developer Mash'
    BREEDER_MASH = 'Breeder Mash'
    ENERGY_MIX = 'Energy Mix'
    UNLINKED_FORMULA = 'Unlinked Formula'
    CUSTOM_MIX = 'Custom Mix'
    MIX_NAME_CHOICES = [
        (LAYER_FORMULA, 'Layer Formula'),
        (GROWER_FORMULA, 'Grower Formula'),
        (PROTEIN_MIX, 'Protein Mix'),
        (CHICK_STARTER, 'Chick Starter'),
        (BROILER_STARTER, 'Broiler Starter'),
        (BROILER_GROWER, 'Broiler Grower'),
        (BROILER_FINISHER, 'Broiler Finisher'),
        (LAYER_MASH, 'Layer Mash'),
        (GROWER_MASH, 'Grower Mash'),
        (DEVELOPER_MASH, 'Developer Mash'),
        (BREEDER_MASH, 'Breeder Mash'),
        (ENERGY_MIX, 'Energy Mix'),
        (EMPTY_FORMULA, 'Empty Formula'),
        (UNLINKED_FORMULA, 'Unlinked Formula'),
        (CUSTOM_MIX, 'Custom Mix'),
    ]
    MIX_INGREDIENTS = {
        LAYER_FORMULA: ['Maize Bran', 'Whole Maize', 'Maize Germ', 'Wheat Bran', 'Rice Bran', 'Soya', 'Soybean Meal', 'Cotton Cake', 'Sunflower Cake', 'Concentrate', 'Fish Meal', 'Blood Meal', 'Bone Meal', 'Meat And Bone Meal', 'Shell', 'Oyster Shell', 'Limestone', 'DCP', 'Salt', 'Vitamin Premix', 'Mineral Premix', 'Lysine', 'Methionine', 'Toxin Binder'],
        GROWER_FORMULA: ['Maize Bran', 'Whole Maize', 'Maize Germ', 'Wheat Bran', 'Wheat Pollard', 'Soya', 'Soybean Meal', 'Cotton Cake', 'Groundnut Cake', 'Concentrate', 'Fish Meal', 'Bone Meal', 'Salt', 'Vitamin Premix', 'Mineral Premix', 'Lysine', 'Methionine'],
        PROTEIN_MIX: ['Soya', 'Soybean Meal', 'Cotton Cake', 'Groundnut Cake', 'Sunflower Cake', 'Sesame Cake', 'Palm Kernel Cake', 'Concentrate', 'Fish Meal', 'Blood Meal', 'Bone Meal', 'Meat And Bone Meal', 'Vitamin Premix', 'Amino Acid Premix', 'Lysine', 'Methionine'],
        CHICK_STARTER: ['Chick Starter', 'Chick Mash', 'Maize Bran', 'Whole Maize', 'Soya', 'Soybean Meal', 'Fish Meal', 'Blood Meal', 'Bone Meal', 'DCP', 'Vitamin Premix', 'Mineral Premix', 'Lysine', 'Methionine'],
        BROILER_STARTER: ['Broiler Starter', 'Broiler Pellets', 'Maize Bran', 'Whole Maize', 'Soya', 'Soybean Meal', 'Fish Meal', 'Blood Meal', 'Bone Meal', 'DCP', 'Vitamin Premix', 'Mineral Premix', 'Lysine', 'Methionine'],
        BROILER_GROWER: ['Broiler Grower', 'Broiler Pellets', 'Maize Bran', 'Whole Maize', 'Wheat Bran', 'Soya', 'Soybean Meal', 'Cotton Cake', 'Groundnut Cake', 'Concentrate', 'Bone Meal', 'DCP', 'Vitamin Premix', 'Lysine', 'Methionine'],
        BROILER_FINISHER: ['Broiler Finisher', 'Broiler Pellets', 'Maize Bran', 'Whole Maize', 'Wheat Bran', 'Soya', 'Soybean Meal', 'Cotton Cake', 'Groundnut Cake', 'Concentrate', 'Bone Meal', 'DCP', 'Vitamin Premix', 'Lysine', 'Methionine'],
        LAYER_MASH: ['Layer Mash', 'Layer Pellets', 'Maize Bran', 'Whole Maize', 'Maize Germ', 'Wheat Bran', 'Soya', 'Soybean Meal', 'Cotton Cake', 'Shell', 'Oyster Shell', 'Limestone', 'DCP', 'Salt', 'Vitamin Premix', 'Mineral Premix', 'Lysine', 'Methionine'],
        GROWER_MASH: ['Grower Mash', 'Grower Pellets', 'Maize Bran', 'Whole Maize', 'Wheat Bran', 'Soya', 'Soybean Meal', 'Cotton Cake', 'Concentrate', 'Salt', 'Vitamin Premix', 'Mineral Premix'],
        DEVELOPER_MASH: ['Maize Bran', 'Whole Maize', 'Wheat Bran', 'Wheat Pollard', 'Soya', 'Soybean Meal', 'Cotton Cake', 'Concentrate', 'Bone Meal', 'DCP', 'Salt', 'Vitamin Premix', 'Mineral Premix'],
        BREEDER_MASH: ['Maize Bran', 'Whole Maize', 'Soya', 'Soybean Meal', 'Cotton Cake', 'Fish Meal', 'Bone Meal', 'Shell', 'Oyster Shell', 'Limestone', 'DCP', 'Vitamin Premix', 'Mineral Premix', 'Lysine', 'Methionine'],
        ENERGY_MIX: ['Maize Bran', 'Whole Maize', 'Maize Germ', 'Wheat Bran', 'Wheat Pollard', 'Rice Bran', 'Broken Rice', 'Sorghum', 'Millet', 'Cassava Flour', 'Sunflower Cake', 'Concentrate', 'Molasses'],
        CUSTOM_MIX: [item_name for item_name, _ in Purchase.ITEM_NAME_CHOICES],
    }

    mix_name = models.CharField(max_length=120, choices=MIX_NAME_CHOICES)
    item_name = models.CharField(max_length=120, choices=Purchase.ITEM_NAME_CHOICES, default='Maize Bran')
    purchase = models.ForeignKey(
        Purchase,
        on_delete=models.PROTECT,
        related_name='feed_mixes',
        null=True,
        blank=True,
    )
    mixing_date = models.DateField(default=timezone.localdate)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, editable=False, default=0)
    stock = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ['-mixing_date', 'mix_name']

    @property
    def total_quantity(self):
        detail_total = self.details.aggregate(total=Sum('quantity'))['total']
        return detail_total if detail_total is not None else self.quantity

    @property
    def total_cost(self):
        detail_total = self.details.aggregate(total=Sum('total_price'))['total']
        return detail_total if detail_total is not None else self.total_amount

    @property
    def total_unit_price(self):
        detail_total = self.details.aggregate(total=Sum('unit_price'))['total']
        return detail_total if detail_total is not None else self.unit_price

    @property
    def price_per_kg(self):
        quantity = self.total_quantity
        if not quantity:
            return Decimal('0')
        return self.total_cost / quantity

    @property
    def allowed_item_names(self):
        return self.MIX_INGREDIENTS.get(self.mix_name, [])

    def latest_item_purchase(self):
        return Purchase.objects.filter(item_name=self.item_name).order_by('-purchase_date', '-created_at').first()

    def adjust_stock(self, quantity):
        self.stock = (self.stock or Decimal('0')) + Decimal(quantity)
        self.save(update_fields=['stock', 'updated_at'])

    def save(self, *args, **kwargs):
        latest_purchase = self.latest_item_purchase()
        if latest_purchase:
            self.unit_price = latest_purchase.unit_price
        self.total_amount = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.mix_name} - {self.mixing_date}'


class FeedMixDetail(TimeStampedModel):
    feed_mix = models.ForeignKey(FeedMix, on_delete=models.CASCADE, related_name='details')
    purchase = models.ForeignKey(
        Purchase,
        on_delete=models.PROTECT,
        related_name='feed_mix_details',
        null=True,
        blank=True,
    )
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name='feed_mix_details')
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit = models.CharField(max_length=30, default='kg')
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, editable=False, default=0)

    class Meta:
        ordering = ['inventory_item__item_name']

    def _stock_delta(self):
        if not self.pk:
            return -self.quantity
        previous = FeedMixDetail.objects.filter(pk=self.pk).values('inventory_item_id', 'quantity').first()
        if not previous:
            return -self.quantity
        if previous['inventory_item_id'] != self.inventory_item_id:
            old_item = InventoryItem.objects.filter(pk=previous['inventory_item_id']).first()
            if old_item:
                old_item.adjust_stock(previous['quantity'])
            return -self.quantity
        return previous['quantity'] - self.quantity

    def _purchase_stock_delta(self):
        if not self.purchase_id:
            return None
        if not self.pk:
            return -self.quantity
        previous = FeedMixDetail.objects.filter(pk=self.pk).values('purchase_id', 'quantity').first()
        if not previous:
            return -self.quantity
        if previous['purchase_id'] != self.purchase_id:
            old_purchase = Purchase.objects.filter(pk=previous['purchase_id']).first()
            if old_purchase:
                old_purchase.adjust_stock_balance(previous['quantity'])
            return -self.quantity
        return previous['quantity'] - self.quantity

    def save(self, *args, **kwargs):
        if self.purchase_id:
            self.inventory_item = self.purchase.inventory_item
            self.unit_price = self.purchase.unit_price
        self.unit = self.inventory_item.unit
        delta = self._stock_delta()
        purchase_delta = self._purchase_stock_delta()
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)
        if delta:
            self.inventory_item.adjust_stock(delta)
        if self.purchase_id and purchase_delta:
            self.purchase.adjust_stock_balance(purchase_delta)

    def delete(self, *args, **kwargs):
        item = self.inventory_item
        purchase = self.purchase
        quantity = self.quantity
        super().delete(*args, **kwargs)
        item.adjust_stock(quantity)
        if purchase:
            purchase.adjust_stock_balance(quantity)

    def __str__(self):
        return f'{self.inventory_item.item_name} for {self.feed_mix.mix_name}'


class FeedConsumption(TimeStampedModel):
    flock = models.ForeignKey(Flock, on_delete=models.PROTECT, related_name='feed_consumptions')
    feed_mix = models.ForeignKey(FeedMix, on_delete=models.PROTECT, related_name='consumptions', null=True, blank=True)
    consumption_date = models.DateField(default=timezone.localdate)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    issued_by = models.CharField(max_length=100)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ['-consumption_date']

    def _stock_delta(self):
        if not self.feed_mix_id:
            return Decimal('0')
        if not self.pk:
            return -self.quantity
        previous = FeedConsumption.objects.filter(pk=self.pk).values('feed_mix_id', 'quantity').first()
        if not previous:
            return -self.quantity
        if previous['feed_mix_id'] != self.feed_mix_id:
            old_mix = FeedMix.objects.filter(pk=previous['feed_mix_id']).first()
            if old_mix:
                old_mix.adjust_stock(previous['quantity'])
            return -self.quantity
        return previous['quantity'] - self.quantity

    def save(self, *args, **kwargs):
        delta = self._stock_delta()
        super().save(*args, **kwargs)
        if self.feed_mix_id and delta:
            self.feed_mix.adjust_stock(delta)

    def delete(self, *args, **kwargs):
        feed_mix = self.feed_mix
        quantity = self.quantity
        super().delete(*args, **kwargs)
        if feed_mix:
            feed_mix.adjust_stock(quantity)

    def __str__(self):
        return f'{self.flock} consumed {self.quantity} on {self.consumption_date}'


EGGS_PER_TRAY = Decimal('30')


class EggProduction(TimeStampedModel):
    detail_properties = ['sold_eggs', 'egg_balance', 'tray_balance', 'loose_egg_balance']

    flock = models.ForeignKey(Flock, on_delete=models.PROTECT, related_name='egg_productions')
    production_date = models.DateField(default=timezone.localdate)
    eggs_collected = models.PositiveIntegerField(default=0)
    broken_eggs = models.PositiveIntegerField(default=0)
    dirty_eggs = models.PositiveIntegerField(default=0)
    good_eggs = models.PositiveIntegerField(editable=False, default=0)

    class Meta:
        ordering = ['-production_date']
        unique_together = [('flock', 'production_date')]

    def save(self, *args, **kwargs):
        rejected = self.broken_eggs + self.dirty_eggs
        self.good_eggs = max(self.eggs_collected - rejected, 0)
        super().save(*args, **kwargs)

    @property
    def sold_eggs(self):
        tray_quantity = self.egg_sales.filter(sale_type=EggSale.TRAY).aggregate(total=Sum('quantity'))['total'] or Decimal('0')
        egg_quantity = self.egg_sales.filter(sale_type=EggSale.EGG).aggregate(total=Sum('quantity'))['total'] or Decimal('0')
        return (tray_quantity * EGGS_PER_TRAY) + egg_quantity

    @property
    def egg_balance(self):
        return max(Decimal(self.good_eggs or 0) - self.sold_eggs, Decimal('0'))

    @property
    def tray_balance(self):
        return self.egg_balance // EGGS_PER_TRAY

    @property
    def loose_egg_balance(self):
        return self.egg_balance % EGGS_PER_TRAY

    def __str__(self):
        return f'{self.production_date} - {self.good_eggs} good eggs'


class EggPrice(TimeStampedModel):
    TRAY = 'Tray'
    EGG = 'Egg'
    SALE_TYPE_CHOICES = [
        (TRAY, 'Tray'),
        (EGG, 'Egg'),
    ]

    sale_type = models.CharField(max_length=20, choices=SALE_TYPE_CHOICES)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    effective_date = models.DateField(default=timezone.localdate)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-effective_date', 'sale_type']

    def __str__(self):
        status = 'Active' if self.is_active else 'Inactive'
        return f'{self.sale_type} - {self.rate} ({status})'


class EggSale(TimeStampedModel):
    TRAY = 'Tray'
    EGG = 'Egg'
    SALE_TYPE_CHOICES = [
        (TRAY, 'Tray'),
        (EGG, 'Egg'),
    ]

    egg_production = models.ForeignKey(
        EggProduction,
        on_delete=models.PROTECT,
        related_name='egg_sales',
        null=True,
        blank=True,
    )
    egg_price = models.ForeignKey(
        EggPrice,
        on_delete=models.PROTECT,
        related_name='egg_sales',
        null=True,
        blank=True,
    )
    sale_date = models.DateField(default=timezone.localdate)
    sale_type = models.CharField(max_length=20, choices=SALE_TYPE_CHOICES)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, editable=False, default=0)
    payment_method = models.CharField(max_length=50, default='Cash')

    class Meta:
        ordering = ['-sale_date']

    def save(self, *args, **kwargs):
        if self.egg_price_id:
            self.rate = self.egg_price.rate
        self.total_amount = self.quantity * self.rate
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.sale_date} - {self.quantity} {self.sale_type}'


class Income(TimeStampedModel):
    income_date = models.DateField(default=timezone.localdate)
    income_type = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ['-income_date']

    def __str__(self):
        return f'{self.income_type} - {self.amount}'


class Expense(TimeStampedModel):
    expense_date = models.DateField(default=timezone.localdate)
    category = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=50, default='Cash')

    class Meta:
        ordering = ['-expense_date']

    def __str__(self):
        return f'{self.category} - {self.amount}'


class ProfitSnapshot(TimeStampedModel):
    DAILY = 'Daily'
    WEEKLY = 'Weekly'
    MONTHLY = 'Monthly'
    YEARLY = 'Yearly'
    PERIOD_CHOICES = [
        (DAILY, 'Daily'),
        (WEEKLY, 'Weekly'),
        (MONTHLY, 'Monthly'),
        (YEARLY, 'Yearly'),
    ]

    period_type = models.CharField(max_length=20, choices=PERIOD_CHOICES)
    period_start = models.DateField()
    period_end = models.DateField()
    total_income = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_expenses = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_profit = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ['-period_start']

    @classmethod
    def build_for_period(cls, period_type, start_date=None):
        start = start_date or timezone.localdate()
        if period_type == cls.WEEKLY:
            end = start + timedelta(days=6)
        elif period_type == cls.MONTHLY:
            if start.month == 12:
                end = date(start.year, 12, 31)
            else:
                end = date(start.year, start.month + 1, 1) - timedelta(days=1)
        elif period_type == cls.YEARLY:
            end = date(start.year, 12, 31)
        else:
            end = start

        egg_sales = EggSale.objects.filter(sale_date__range=(start, end)).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
        income = Income.objects.filter(income_date__range=(start, end)).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        expenses = Expense.objects.filter(expense_date__range=(start, end)).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        purchases = Purchase.objects.filter(purchase_date__range=(start, end)).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
        total_income = egg_sales + income
        total_expenses = expenses + purchases

        return cls(
            period_type=period_type,
            period_start=start,
            period_end=end,
            total_income=total_income,
            total_expenses=total_expenses,
            net_profit=total_income - total_expenses,
        )

    def save(self, *args, **kwargs):
        self.net_profit = self.total_income - self.total_expenses
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.period_type}: {self.period_start} to {self.period_end}'


class AuditLog(TimeStampedModel):
    CREATE = 'Create'
    UPDATE = 'Update'
    DELETE = 'Delete'
    ACTION_CHOICES = [
        (CREATE, 'Create'),
        (UPDATE, 'Update'),
        (DELETE, 'Delete'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model_label = models.CharField(max_length=120)
    object_id = models.CharField(max_length=64)
    object_repr = models.CharField(max_length=255)
    request_path = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        actor = self.user or 'Unknown user'
        return f'{actor} {self.action.lower()}d {self.model_label} #{self.object_id}'
