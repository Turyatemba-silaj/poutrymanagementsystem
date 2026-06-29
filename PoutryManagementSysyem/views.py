from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group, Permission
from django import forms
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.forms import BaseFormSet, formset_factory, modelform_factory
from django.db import transaction
from django.db.models import Sum
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .payment_gateways import GATEWAYS, PaymentGatewayError, provider_options
from .models import (
    AuditLog,
    EggProduction,
    EggPrice,
    EggSale,
    EGGS_PER_TRAY,
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


User = get_user_model()


CRUD_MODELS = {
    'houses': {
        'model': PoultryHouse,
        'title': 'Poultry Houses',
        'singular': 'Poultry House',
        'columns': ['id', 'house_name', 'capacity', 'bird_type', 'status'],
    },
    'flocks': {
        'model': Flock,
        'title': 'Flocks',
        'singular': 'Flock',
        'columns': ['id', 'breed', 'house', 'purchase_date', 'number_of_birds', 'current_birds', 'balance', 'remarks_status'],
    },
    'purchases': {
        'model': Purchase,
        'title': 'Purchases',
        'singular': 'Purchase',
        'columns': ['id', 'purchase_date', 'item_name', 'category', 'quantity', 'unit_price', 'total_amount', 'stock_balance'],
    },
    'feed-mixes': {
        'model': FeedMix,
        'title': 'Feed Mixes',
        'singular': 'Feed Mix',
        'columns': ['id', 'mix_name', 'mixing_date', 'total_quantity', 'total_unit_price', 'total_cost', 'stock'],
    },
    'feed-mix-details': {
        'model': FeedMixDetail,
        'title': 'Feed Mixing Details',
        'singular': 'Feed Mixing Detail',
        'columns': ['id', 'feed_mix', 'purchase', 'quantity', 'unit_price', 'total_price'],
    },
    'feed-consumption': {
        'model': FeedConsumption,
        'title': 'Feed Consumption',
        'singular': 'Feed Consumption',
        'columns': ['id', 'consumption_date', 'flock', 'feed_mix', 'quantity', 'issued_by'],
    },
    'egg-production': {
        'model': EggProduction,
        'title': 'Egg Production',
        'singular': 'Egg Production',
        'columns': ['id', 'production_date', 'flock', 'eggs_collected', 'broken_eggs', 'dirty_eggs', 'good_eggs', 'egg_balance', 'tray_balance'],
    },
    'egg-prices': {
        'model': EggPrice,
        'title': 'Egg Prices',
        'singular': 'Egg Price',
        'columns': ['id', 'sale_type', 'rate', 'effective_date', 'is_active'],
    },
    'egg-sales': {
        'model': EggSale,
        'title': 'Egg Sales',
        'singular': 'Egg Sale',
        'columns': ['id', 'sale_date', 'sale_type', 'quantity', 'rate', 'total_amount', 'payment_method'],
    },
    'income': {
        'model': Income,
        'title': 'Income',
        'singular': 'Income',
        'columns': ['id', 'income_date', 'income_type', 'amount'],
    },
    'expenses': {
        'model': Expense,
        'title': 'Expenses',
        'singular': 'Expense',
        'columns': ['id', 'expense_date', 'category', 'amount', 'payment_method'],
    },
    'audit-logs': {
        'model': AuditLog,
        'title': 'Audit Logs',
        'singular': 'Audit Log',
        'columns': ['id', 'created_at', 'user', 'action', 'model_label', 'object_id', 'object_repr', 'request_path'],
        'read_only': True,
    },
}


def get_crud_config(slug):
    return CRUD_MODELS.get(slug)


def model_permission(model, action):
    return f'{model._meta.app_label}.{action}_{model._meta.model_name}'


def has_model_permission(user, model, action):
    return user.has_perm(model_permission(model, action))


def require_model_permission(request, model, action):
    if not has_model_permission(request.user, model, action):
        raise PermissionDenied


def write_audit_log(request, action, obj, object_repr=None):
    user = request.user if request.user.is_authenticated else None
    AuditLog.objects.create(
        user=user,
        action=action,
        model_label=obj._meta.label,
        object_id=str(obj.pk),
        object_repr=(object_repr or str(obj))[:255],
        request_path=request.path[:255],
    )


MIN_TRAY_BALANCE = Decimal('5')
MIN_LOOSE_EGG_BALANCE = Decimal('20')


def egg_sale_quantity_as_eggs(sale_type, quantity):
    quantity = Decimal(quantity or 0)
    if sale_type == EggSale.TRAY:
        return quantity * EGGS_PER_TRAY
    return quantity


def egg_sale_queryset_quantity_as_eggs(queryset):
    tray_quantity = queryset.filter(sale_type=EggSale.TRAY).aggregate(total=Sum('quantity'))['total'] or Decimal('0')
    egg_quantity = queryset.filter(sale_type=EggSale.EGG).aggregate(total=Sum('quantity'))['total'] or Decimal('0')
    return (tray_quantity * EGGS_PER_TRAY) + egg_quantity


def available_good_eggs(egg_production=None, excluding_sale=None):
    if egg_production:
        produced = Decimal(egg_production.good_eggs or 0)
        sold_queryset = EggSale.objects.filter(egg_production=egg_production)
    else:
        produced = Decimal(EggProduction.objects.aggregate(total=Sum('good_eggs'))['total'] or 0)
        sold_queryset = EggSale.objects.all()
    if excluding_sale and excluding_sale.pk:
        sold_queryset = sold_queryset.exclude(pk=excluding_sale.pk)
    return produced - egg_sale_queryset_quantity_as_eggs(sold_queryset)


class UserCreateForm(UserCreationForm):
    email = forms.EmailField(required=False)
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.order_by('name'),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Roles',
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'groups')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')

    def save(self, commit=True):
        groups = self.cleaned_data.get('groups')
        user = super().save(commit=commit)
        user.email = self.cleaned_data.get('email', '')
        user.first_name = self.cleaned_data.get('first_name', '')
        user.last_name = self.cleaned_data.get('last_name', '')
        if commit:
            user.save()
            user.groups.set(groups)
        return user


class RoleForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.select_related('content_type').order_by(
            'content_type__app_label',
            'content_type__model',
            'codename',
        ),
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    class Meta:
        model = Group
        fields = ['name', 'permissions']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')


class UserRoleForm(forms.ModelForm):
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.order_by('name'),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Roles',
    )

    class Meta:
        model = User
        fields = ['groups']


def editable_field_names(model):
    excluded_fields = {'id', 'created_at', 'updated_at'}
    if model is Purchase:
        excluded_fields.add('inventory_item')
        excluded_fields.add('unit')
        excluded_fields.add('stock_balance')
    if model is FeedMix:
        excluded_fields.add('item_name')
        excluded_fields.add('purchase')
        excluded_fields.add('remarks')
        excluded_fields.add('quantity')
        excluded_fields.add('unit_price')
        excluded_fields.add('stock')
    if model is FeedMixDetail:
        excluded_fields.add('inventory_item')
        excluded_fields.add('unit')
        excluded_fields.add('unit_price')
    return [
        field.name
        for field in model._meta.fields
        if field.editable and field.name not in excluded_fields
    ]


def build_form_class(model):
    form_class = modelform_factory(model, fields=editable_field_names(model))

    class StyledForm(form_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if model is FeedMix and 'item_name' in self.fields:
                purchased_item_names = list(
                    Purchase.objects.order_by('item_name').values_list('item_name', flat=True).distinct()
                )
                submitted_item_name = self.data.get('item_name') if self.is_bound else None
                if submitted_item_name and submitted_item_name not in purchased_item_names:
                    purchased_item_names.append(submitted_item_name)
                if self.instance and self.instance.pk and self.instance.item_name not in purchased_item_names:
                    purchased_item_names.append(self.instance.item_name)
                self.fields['item_name'].choices = [(item_name, item_name) for item_name in purchased_item_names]
            if model is FeedMixDetail and 'purchase' in self.fields:
                self.fields['purchase'].label = 'Purchased Item'
                self.fields['purchase'].queryset = Purchase.objects.select_related('inventory_item').order_by(
                    '-purchase_date',
                    '-created_at',
                )
            for field_name, field in self.fields.items():
                widget = field.widget
                widget.attrs.setdefault('class', 'form-control')
                if field_name.endswith('_date'):
                    widget.input_type = 'date'
                if field_name == 'payment_method':
                    field.widget = forms.Select(
                        choices=[
                            ('Cash', 'Cash'),
                            ('Mobile Money', 'Mobile Money'),
                            ('Bank Transfer', 'Bank Transfer'),
                            ('Credit', 'Credit'),
                        ],
                        attrs={'class': 'form-control'},
                    )

        def clean(self):
            cleaned_data = super().clean()
            if model is FeedMix:
                item_name = cleaned_data.get('item_name')
                quantity = cleaned_data.get('quantity') or Decimal('0')
                if item_name and quantity > 0 and not Purchase.objects.filter(item_name=item_name).exists():
                    raise forms.ValidationError(f'Add {item_name} in Purchases before using it in Feed Mixes.')
            if model is FeedMixDetail:
                feed_mix = cleaned_data.get('feed_mix')
                purchase = cleaned_data.get('purchase')
                if feed_mix and not purchase:
                    raise forms.ValidationError('Select a purchased item for this feed mix.')
                if feed_mix and purchase and purchase.item_name not in feed_mix.allowed_item_names:
                    raise forms.ValidationError(f'{purchase.item_name} is not part of the {feed_mix.mix_name} recipe.')
            if model is FeedConsumption:
                feed_mix = cleaned_data.get('feed_mix')
                quantity = cleaned_data.get('quantity') or Decimal('0')
                if feed_mix and quantity > 0:
                    previous_quantity = Decimal('0')
                    if self.instance and self.instance.pk and self.instance.feed_mix_id == feed_mix.pk:
                        previous_quantity = self.instance.quantity or Decimal('0')
                    available_stock = feed_mix.stock + previous_quantity
                    if quantity > available_stock:
                        raise forms.ValidationError(
                            f'Feed consumption quantity ({format_decimal(quantity)}kg) '
                            f'cannot exceed feed mix stock ({format_decimal(available_stock)}kg).'
                        )
            if model is EggSale:
                egg_price = cleaned_data.get('egg_price')
                egg_production = cleaned_data.get('egg_production')
                sale_type = egg_price.sale_type if egg_price else cleaned_data.get('sale_type')
                quantity = cleaned_data.get('quantity') or Decimal('0')
                requested_eggs = egg_sale_quantity_as_eggs(sale_type, quantity)
                available_eggs = available_good_eggs(egg_production, self.instance)
                if requested_eggs > available_eggs:
                    if egg_production:
                        produced_eggs = Decimal(egg_production.good_eggs or 0)
                        sold_eggs = produced_eggs - available_eggs
                        stock_message = (
                            f'This production has {format_decimal(produced_eggs)} good eggs, '
                            f'{format_decimal(sold_eggs)} already sold, '
                            f'{format_decimal(max(available_eggs, Decimal("0")))} remaining.'
                        )
                    else:
                        stock_message = (
                            f'Available good eggs across all production is '
                            f'{format_decimal(max(available_eggs, Decimal("0")))}.'
                        )
                    raise forms.ValidationError(
                        f'Egg sale quantity ({format_decimal(requested_eggs)} eggs) cannot exceed available good eggs. '
                        f'{stock_message}'
                    )
            return cleaned_data

    return StyledForm


class PurchaseItemNameChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.item_name


class FeedMixIngredientForm(forms.Form):
    purchase = PurchaseItemNameChoiceField(
        queryset=Purchase.objects.none(),
        required=False,
        label='Food',
    )
    quantity = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal('0.01'),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['purchase'].queryset = Purchase.objects.select_related('inventory_item').order_by(
            'item_name',
            '-purchase_date',
            '-created_at',
        )
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'form-control')

    def clean(self):
        cleaned_data = super().clean()
        purchase = cleaned_data.get('purchase')
        quantity = cleaned_data.get('quantity')
        marked_for_delete = cleaned_data.get('DELETE')
        if marked_for_delete:
            return cleaned_data
        if purchase and not quantity:
            raise forms.ValidationError('Enter the quantity for this food.')
        if quantity and not purchase:
            raise forms.ValidationError('Select the food for this quantity.')
        return cleaned_data


class BaseFeedMixIngredientFormSet(BaseFormSet):
    def __init__(self, *args, **kwargs):
        self.feed_mix = kwargs.pop('feed_mix', None)
        super().__init__(*args, **kwargs)

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        quantities_by_purchase = {}
        for ingredient_form in self.forms:
            cleaned_data = ingredient_form.cleaned_data
            if not cleaned_data or cleaned_data.get('DELETE'):
                continue
            purchase = cleaned_data.get('purchase')
            quantity = cleaned_data.get('quantity')
            if not purchase or not quantity:
                continue
            quantities_by_purchase[purchase] = quantities_by_purchase.get(purchase, Decimal('0')) + quantity

        for purchase, quantity in quantities_by_purchase.items():
            existing_quantity = Decimal('0')
            if self.feed_mix and self.feed_mix.pk:
                existing_quantity = (
                    FeedMixDetail.objects.filter(feed_mix=self.feed_mix, purchase=purchase).aggregate(total=Sum('quantity'))['total']
                    or Decimal('0')
                )
            available_quantity = purchase.stock_balance + existing_quantity
            if quantity > available_quantity:
                raise forms.ValidationError(
                    f'{purchase.item_name} feed mix quantity ({format_decimal(quantity)}kg) '
                    f'cannot exceed purchase stock balance ({format_decimal(available_quantity)}kg).'
                )


FeedMixIngredientFormSet = formset_factory(
    FeedMixIngredientForm,
    formset=BaseFeedMixIngredientFormSet,
    can_delete=True,
    extra=1,
)


def format_label(value):
    labels = {
        'inventory_item': 'Purchased Item',
        'purchase': 'Purchased Item',
        'total_quantity': 'Quantity',
        'total_unit_price': 'Unit Price',
        'total_cost': 'Total Amount',
        'stock': 'Stock',
        'number_of_birds': 'Number Of Birds Purchased',
        'remarks_status': 'Remarks',
    }
    if value in labels:
        return labels[value]
    return value.replace('_', ' ').title()


def format_decimal(value):
    decimal_value = Decimal(value)
    if decimal_value == decimal_value.to_integral():
        return f'{decimal_value:,.0f}'
    return f'{decimal_value.normalize():,f}'


def display_unit(unit, quantity):
    units = {
        'kg': 'kg' if Decimal(quantity) == Decimal('1') else 'kgs',
        'pc': 'pc' if Decimal(quantity) == Decimal('1') else 'pcs',
        'litre': 'litre' if Decimal(quantity) == Decimal('1') else 'litres',
        'bottle': 'bottle' if Decimal(quantity) == Decimal('1') else 'bottles',
    }
    return units.get(unit, unit)


def format_currency(value):
    return f'UGX {Decimal(value):,.0f}'


def format_quantity_with_unit(quantity, unit):
    return f'{format_decimal(quantity)}{display_unit(unit, quantity)}'


def format_cell_value(obj, column):
    value = getattr(obj, column)
    if isinstance(obj, Purchase):
        if column == 'quantity':
            return format_quantity_with_unit(value, obj.unit)
        if column == 'stock_balance':
            return format_quantity_with_unit(value, obj.unit)
        if column in {'unit_price', 'total_amount'}:
            return format_currency(value)
    if isinstance(obj, FeedMix):
        if column == 'purchase':
            purchase = obj.purchase
            if purchase:
                return f'{purchase.item_name} - {format_quantity_with_unit(purchase.quantity, purchase.unit)} @ {format_currency(purchase.unit_price)}'
            return '-'
        if column in {'quantity', 'total_quantity', 'stock'}:
            return format_quantity_with_unit(value, 'kg')
        if column == 'unit_price' and not value:
            latest_purchase = obj.latest_item_purchase()
            if latest_purchase:
                return format_currency(latest_purchase.unit_price)
        if column in {'unit_price', 'total_amount', 'total_unit_price', 'total_cost', 'price_per_kg'}:
            return format_currency(value)
    if isinstance(obj, FeedMixDetail):
        if column == 'purchase':
            purchase = obj.purchase
            if purchase:
                return f'{purchase.item_name} - {format_quantity_with_unit(purchase.quantity, purchase.unit)} @ {format_currency(purchase.unit_price)}'
            return obj.inventory_item
        if column == 'quantity':
            return format_quantity_with_unit(value, obj.unit)
        if column in {'unit_price', 'total_price'}:
            return format_currency(value)
    if isinstance(obj, EggProduction):
        if column in {'sold_eggs', 'egg_balance', 'loose_egg_balance'}:
            return f'{format_decimal(value)} eggs'
        if column == 'tray_balance':
            return f'{format_decimal(value)} trays'
    return value


def low_stock_notifications():
    notifications = []
    for item in InventoryItem.objects.all():
        if not item.needs_reorder:
            continue
        balance = format_quantity_with_unit(item.current_stock, item.unit)
        notifications.append({
            'item_name': item.item_name,
            'balance': balance,
            'message': f'{item.item_name} balance is low at {balance}. {item.item_name} needs refill.',
        })
    good_egg_balance = max(available_good_eggs(), Decimal('0'))
    available_trays = good_egg_balance // EGGS_PER_TRAY
    loose_eggs = good_egg_balance % EGGS_PER_TRAY
    if available_trays < MIN_TRAY_BALANCE:
        notifications.append({
            'item_name': 'Egg trays',
            'balance': f'{format_decimal(available_trays)} trays',
            'message': (
                f'Egg tray balance is low at {format_decimal(available_trays)} trays. '
                f'Minimum tray balance is {format_decimal(MIN_TRAY_BALANCE)} trays.'
            ),
        })
    if loose_eggs < MIN_LOOSE_EGG_BALANCE:
        notifications.append({
            'item_name': 'Loose eggs',
            'balance': f'{format_decimal(loose_eggs)} eggs',
            'message': (
                f'Loose egg balance is low at {format_decimal(loose_eggs)} eggs. '
                f'Minimum loose egg balance is {format_decimal(MIN_LOOSE_EGG_BALANCE)} eggs.'
            ),
        })
    return notifications


def feed_item_price_options(model_slug):
    options = {}
    if model_slug == 'feed-mix-details':
        purchases = Purchase.objects.select_related('inventory_item').order_by('-purchase_date', '-created_at')
        for purchase in purchases:
            options[str(purchase.pk)] = {
                'unit_price': str(purchase.unit_price),
                'unit': purchase.unit,
                'stock': format_quantity_with_unit(purchase.stock_balance, purchase.unit),
                'item_name': purchase.item_name,
            }
    return options


def feed_mix_purchase_options():
    options = {}
    purchases = Purchase.objects.order_by('-purchase_date', '-created_at')
    for feed_mix in FeedMix.objects.all():
        allowed_items = set(feed_mix.allowed_item_names)
        options[str(feed_mix.pk)] = [
            purchase.pk
            for purchase in purchases
            if purchase.item_name in allowed_items
        ]
    return options


def feed_mix_recipe_purchase_options():
    purchase_ids = list(
        Purchase.objects.order_by('item_name', '-purchase_date', '-created_at').values_list('pk', flat=True)
    )
    return {
        mix_name: purchase_ids
        for mix_name, _ in FeedMix.MIX_NAME_CHOICES
    }


def feed_mix_item_prices():
    prices = {}
    purchases = Purchase.objects.order_by('-purchase_date', '-created_at')
    for purchase in purchases:
        if purchase.item_name in prices:
            continue
        prices[purchase.item_name] = str(purchase.unit_price)
    return prices


def feed_mix_purchase_prices():
    prices = {}
    purchases = Purchase.objects.select_related('inventory_item').order_by('item_name', '-purchase_date', '-created_at')
    for purchase in purchases:
        prices[str(purchase.pk)] = {
            'unit_price': str(purchase.unit_price),
            'item_name': purchase.item_name,
            'unit': purchase.unit,
            'stock': format_quantity_with_unit(purchase.stock_balance, purchase.unit),
        }
    return prices


def feed_mix_detail_initial(feed_mix):
    return [
        {
            'purchase': detail.purchase_id,
            'quantity': detail.quantity,
        }
        for detail in feed_mix.details.select_related('purchase').order_by('purchase__item_name')
        if detail.purchase_id
    ]


def update_feed_mix_totals(feed_mix, previous_quantity=None):
    quantity = feed_mix.total_quantity
    unit_price = feed_mix.total_unit_price
    total_amount = feed_mix.total_cost
    if previous_quantity is None:
        stock = feed_mix.stock
    else:
        stock = (feed_mix.stock or Decimal('0')) + quantity - previous_quantity
    FeedMix.objects.filter(pk=feed_mix.pk).update(
        item_name=feed_mix.item_name,
        quantity=quantity,
        unit_price=unit_price,
        total_amount=total_amount,
        stock=stock,
        updated_at=timezone.now(),
    )
    feed_mix.quantity = quantity
    feed_mix.unit_price = unit_price
    feed_mix.total_amount = total_amount
    feed_mix.stock = stock


def save_feed_mix_ingredients(feed_mix, ingredient_formset):
    previous_quantity = feed_mix.quantity or Decimal('0')
    feed_mix.details.all().delete()
    first_purchase = None
    for ingredient_form in ingredient_formset:
        if not ingredient_form.cleaned_data or ingredient_form.cleaned_data.get('DELETE'):
            continue
        purchase = ingredient_form.cleaned_data.get('purchase')
        quantity = ingredient_form.cleaned_data.get('quantity')
        if not purchase or not quantity:
            continue
        if first_purchase is None:
            first_purchase = purchase
        FeedMixDetail.objects.create(
            feed_mix=feed_mix,
            purchase=purchase,
            inventory_item=purchase.inventory_item,
            quantity=quantity,
        )
    if first_purchase:
        feed_mix.item_name = first_purchase.item_name
    update_feed_mix_totals(feed_mix, previous_quantity)


def ingredient_formset_has_items(ingredient_formset):
    return any(
        ingredient_form.cleaned_data
        and not ingredient_form.cleaned_data.get('DELETE')
        and ingredient_form.cleaned_data.get('purchase')
        and ingredient_form.cleaned_data.get('quantity')
        for ingredient_form in ingredient_formset
    )


def feed_mix_available_item_options():
    purchased_item_names = list(
        Purchase.objects.order_by('item_name').values_list('item_name', flat=True).distinct()
    )
    return {
        mix_name: purchased_item_names
        for mix_name, _ in FeedMix.MIX_NAME_CHOICES
    }


def object_rows(obj):
    hidden_fields = {'id'}
    if isinstance(obj, FeedMix):
        hidden_fields.update({'item_name', 'purchase', 'quantity', 'unit_price', 'total_amount', 'remarks'})
    rows = []
    for field in obj._meta.fields:
        if field.name in hidden_fields:
            continue
        rows.append({
            'label': format_label(field.name),
            'value': format_cell_value(obj, field.name),
        })
    for name in getattr(obj, 'detail_properties', []):
        rows.append({
            'label': format_label(name),
            'value': format_cell_value(obj, name),
        })
    return rows


def list_rows(objects, columns):
    rows = []
    for obj in objects:
        rows.append({
            'object': obj,
            'values': [
                {
                    'label': format_label(column),
                    'value': format_cell_value(obj, column),
                }
                for column in columns
            ],
        })
    return rows


def feed_mix_calculations():
    quantity = total_for(FeedMixDetail.objects.all(), 'quantity')
    unit_price = total_for(FeedMixDetail.objects.all(), 'unit_price')
    price = total_for(FeedMixDetail.objects.all(), 'total_price')
    stock = total_for(FeedMix.objects.all(), 'stock')
    return [
        {'label': 'Total quantity of mixed feeds', 'value': format_quantity_with_unit(quantity, 'kg')},
        {'label': 'Total unit price of mixed feeds', 'value': format_currency(unit_price)},
        {'label': 'Total amount of all items', 'value': format_currency(price)},
        {'label': 'Stock of mixed feeds', 'value': format_quantity_with_unit(stock, 'kg')},
    ]


def list_calculations(model_slug):
    return []


def list_total_row(model_slug):
    if model_slug == 'feed-mixes':
        quantity = total_for(FeedMixDetail.objects.all(), 'quantity')
        unit_price = total_for(FeedMixDetail.objects.all(), 'unit_price')
        price = total_for(FeedMixDetail.objects.all(), 'total_price')
        stock = total_for(FeedMix.objects.all(), 'stock')
        return {
            'label': 'Totals',
            'label_colspan': 3,
            'cells': [
                format_quantity_with_unit(quantity, 'kg'),
                format_currency(unit_price),
                format_currency(price),
                format_quantity_with_unit(stock, 'kg'),
                '',
            ],
        }

    if model_slug != 'feed-mix-details':
        return None

    quantity = total_for(FeedMixDetail.objects.all(), 'quantity')
    price = total_for(FeedMixDetail.objects.all(), 'total_price')
    price_per_kg = Decimal('0') if not quantity else price / quantity
    return {
        'label': 'Totals',
        'quantity': quantity,
        'quantity_display': format_quantity_with_unit(quantity, 'kg'),
        'unit_price': price_per_kg,
        'unit_price_display': format_currency(price_per_kg),
        'total_price': price,
        'total_price_display': format_currency(price),
    }


def mobile_money_confirmation_missing(request, model_slug):
    return (
        model_slug == 'egg-sales'
        and request.POST.get('payment_method') == 'Mobile Money'
        and (
            request.POST.get('mobile_money_confirmed') != '1'
            or not request.POST.get('mobile_money_request_id')
        )
    )


def apply_egg_sale_price(form, model_slug):
    if model_slug != 'egg-sales':
        return
    egg_price = form.cleaned_data.get('egg_price')
    if egg_price:
        form.instance.rate = egg_price.rate
        form.instance.sale_type = egg_price.sale_type


def record_form_context(config, model_slug, form, action, obj=None):
    context = {
        'config': config,
        'model_slug': model_slug,
        'form': form,
        'action': action,
    }
    if obj is not None:
        context['object'] = obj
    if model_slug == 'egg-sales':
        context['egg_price_rates'] = {
            str(item.pk): {
                'rate': str(item.rate),
                'sale_type': item.sale_type,
            }
            for item in EggPrice.objects.filter(is_active=True)
        }
    if model_slug == 'feed-mix-details':
        context['feed_item_prices'] = feed_item_price_options(model_slug)
        context['feed_mix_purchase_options'] = feed_mix_purchase_options()
    if model_slug == 'feed-mixes':
        context['feed_mix_item_options'] = feed_mix_available_item_options()
        context['feed_mix_item_prices'] = feed_mix_item_prices()
        context['feed_mix_purchase_prices'] = feed_mix_purchase_prices()
        context['feed_mix_recipe_purchase_options'] = feed_mix_recipe_purchase_options()
    if model_slug == 'purchases':
        context['purchase_item_categories'] = Purchase.ITEM_CATEGORY_MAP
    return context


def feed_mix_form_context(config, form, ingredient_formset, action, obj=None):
    context = record_form_context(config, 'feed-mixes', form, action, obj)
    context['feed_mix_ingredient_formset'] = ingredient_formset
    return context


def parse_report_date(value):
    if not value:
        return timezone.localdate()
    try:
        return date.fromisoformat(value)
    except ValueError:
        return timezone.localdate()


def total_for(queryset, field):
    return queryset.aggregate(total=Sum(field))['total'] or Decimal('0')


def chart_percent(value, max_value):
    if not max_value:
        return 0
    return int((Decimal(value or 0) / Decimal(max_value)) * 100)


@login_required
@require_GET
def mobile_money_providers(request):
    return JsonResponse({'ok': True, 'providers': provider_options()})


@login_required
@require_POST
def request_mobile_money_payment(request):
    provider = request.POST.get('provider', 'simulator').strip() or 'simulator'
    mobile_number = request.POST.get('mobile_number', '').strip()
    amount_text = request.POST.get('amount', '').strip()

    gateway = GATEWAYS.get(provider)
    if not gateway:
        return JsonResponse({'ok': False, 'message': 'Select a valid mobile money provider.'}, status=400)
    if not gateway.configured():
        return JsonResponse({'ok': False, 'message': f'{gateway.name} API is not configured yet.'}, status=400)
    if not mobile_number:
        return JsonResponse({'ok': False, 'message': 'Enter the mobile money number.'}, status=400)

    try:
        amount = Decimal(amount_text)
    except Exception:
        return JsonResponse({'ok': False, 'message': 'Enter a valid payment amount.'}, status=400)

    if amount <= 0:
        return JsonResponse({'ok': False, 'message': 'Payment amount must be greater than zero.'}, status=400)

    external_id = f'EGGSALE-{timezone.now().strftime("%Y%m%d%H%M%S")}'
    try:
        payment = gateway.request_payment(mobile_number, amount, external_id)
    except PaymentGatewayError as error:
        return JsonResponse({'ok': False, 'message': str(error)}, status=502)

    transaction_id = payment['transaction_id']
    request.session[f'mobile_money:{transaction_id}'] = {
        'provider': provider,
        'mobile_number': mobile_number,
        'amount': str(amount),
        'status': payment['status'],
        'created_at': timezone.now().isoformat(),
    }
    request.session.modified = True
    return JsonResponse({
        'ok': True,
        'status': payment['status'],
        'provider': provider,
        'provider_name': gateway.name,
        'transaction_id': transaction_id,
        'message': payment['message'],
        'simulated': payment.get('simulated', False),
    })


@login_required
@require_GET
def mobile_money_payment_status(request, transaction_id):
    payment = request.session.get(f'mobile_money:{transaction_id}')
    if not payment:
        return JsonResponse({'ok': False, 'message': 'Payment request was not found.'}, status=404)

    gateway = GATEWAYS.get(payment['provider'])
    if gateway and gateway.configured():
        try:
            payment['status'] = gateway.payment_status(transaction_id)
            request.session[f'mobile_money:{transaction_id}'] = payment
            request.session.modified = True
        except PaymentGatewayError as error:
            return JsonResponse({'ok': False, 'message': str(error)}, status=502)

    return JsonResponse({
        'ok': True,
        'transaction_id': transaction_id,
        'status': payment['status'],
        'provider': payment['provider'],
        'amount': payment['amount'],
        'mobile_number': payment['mobile_number'],
    })


@login_required
def home(request):
    context = {
        'houses_count': PoultryHouse.objects.count(),
        'active_flocks_count': Flock.objects.filter(remarks=Flock.AVAILABLE).count(),
        'current_birds': total_for(Flock.objects.filter(remarks=Flock.AVAILABLE), 'current_birds'),
        'stock_items_count': InventoryItem.objects.count(),
    }
    return render(request, 'PoutryManagementSysyem/home.html', context)


@login_required
def crud_index(request):
    return render(request, 'PoutryManagementSysyem/crud_index.html', {
        'configs': CRUD_MODELS,
    })


@login_required
def user_list(request):
    require_model_permission(request, User, 'view')
    users = User.objects.prefetch_related('groups').order_by('username')
    return render(request, 'PoutryManagementSysyem/user_list.html', {
        'users': users,
        'can_add_user': has_model_permission(request.user, User, 'add'),
        'can_change_user': has_model_permission(request.user, User, 'change'),
        'can_view_roles': has_model_permission(request.user, Group, 'view'),
    })


@login_required
def user_create(request):
    require_model_permission(request, User, 'add')
    form = UserCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        write_audit_log(request, AuditLog.CREATE, user)
        messages.success(request, 'User created successfully.')
        return redirect('poultry:user_list')
    return render(request, 'PoutryManagementSysyem/security_form.html', {
        'title': 'Add User',
        'eyebrow': 'Authentication',
        'form': form,
        'back_url': reverse('poultry:user_list'),
        'button_label': 'Save User',
    })


@login_required
def user_assign_roles(request, pk):
    require_model_permission(request, User, 'change')
    user_obj = get_object_or_404(User, pk=pk)
    form = UserRoleForm(request.POST or None, instance=user_obj)
    if request.method == 'POST' and form.is_valid():
        user_obj = form.save()
        write_audit_log(request, AuditLog.UPDATE, user_obj, f'Roles updated for {user_obj}')
        messages.success(request, 'User roles updated successfully.')
        return redirect('poultry:user_list')
    return render(request, 'PoutryManagementSysyem/security_form.html', {
        'title': f'Assign Roles: {user_obj.username}',
        'eyebrow': 'Authorization',
        'form': form,
        'back_url': reverse('poultry:user_list'),
        'button_label': 'Save Roles',
    })


@login_required
def role_list(request):
    require_model_permission(request, Group, 'view')
    roles = Group.objects.prefetch_related('permissions').order_by('name')
    return render(request, 'PoutryManagementSysyem/role_list.html', {
        'roles': roles,
        'can_add_role': has_model_permission(request.user, Group, 'add'),
        'can_change_role': has_model_permission(request.user, Group, 'change'),
    })


@login_required
def role_create(request):
    require_model_permission(request, Group, 'add')
    form = RoleForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        role = form.save()
        write_audit_log(request, AuditLog.CREATE, role)
        messages.success(request, 'Role created successfully.')
        return redirect('poultry:role_list')
    return render(request, 'PoutryManagementSysyem/security_form.html', {
        'title': 'Add Role',
        'eyebrow': 'Authorization',
        'form': form,
        'back_url': reverse('poultry:role_list'),
        'button_label': 'Save Role',
    })


@login_required
def role_update(request, pk):
    require_model_permission(request, Group, 'change')
    role = get_object_or_404(Group, pk=pk)
    form = RoleForm(request.POST or None, instance=role)
    if request.method == 'POST' and form.is_valid():
        role = form.save()
        write_audit_log(request, AuditLog.UPDATE, role)
        messages.success(request, 'Role updated successfully.')
        return redirect('poultry:role_list')
    return render(request, 'PoutryManagementSysyem/security_form.html', {
        'title': f'Edit Role: {role.name}',
        'eyebrow': 'Authorization',
        'form': form,
        'back_url': reverse('poultry:role_list'),
        'button_label': 'Save Role',
    })


@login_required
def record_list(request, model_slug):
    config = get_crud_config(model_slug)
    if not config:
        return redirect('poultry:crud_index')
    require_model_permission(request, config['model'], 'view')
    objects = config['model'].objects.all()
    return render(request, 'PoutryManagementSysyem/record_list.html', {
        'config': config,
        'model_slug': model_slug,
        'columns': [format_label(column) for column in config['columns']],
        'rows': list_rows(objects, config['columns']),
        'calculations': list_calculations(model_slug),
        'total_row': list_total_row(model_slug),
        'can_add': not config.get('read_only') and has_model_permission(request.user, config['model'], 'add'),
        'can_change': not config.get('read_only') and has_model_permission(request.user, config['model'], 'change'),
        'can_delete': not config.get('read_only') and has_model_permission(request.user, config['model'], 'delete'),
    })


@login_required
def record_detail(request, model_slug, pk):
    config = get_crud_config(model_slug)
    if not config:
        return redirect('poultry:crud_index')
    require_model_permission(request, config['model'], 'view')
    obj = get_object_or_404(config['model'], pk=pk)
    return render(request, 'PoutryManagementSysyem/record_detail.html', {
        'config': config,
        'model_slug': model_slug,
        'object': obj,
        'rows': object_rows(obj),
        'can_change': not config.get('read_only') and has_model_permission(request.user, config['model'], 'change'),
        'can_delete': not config.get('read_only') and has_model_permission(request.user, config['model'], 'delete'),
    })


@login_required
def record_create(request, model_slug):
    config = get_crud_config(model_slug)
    if not config:
        return redirect('poultry:crud_index')
    if config.get('read_only'):
        raise PermissionDenied
    require_model_permission(request, config['model'], 'add')
    Form = build_form_class(config['model'])
    if model_slug == 'feed-mixes':
        form = Form(request.POST or None)
        ingredient_formset = FeedMixIngredientFormSet(request.POST or None, prefix='ingredients')
        if request.method == 'POST' and form.is_valid() and ingredient_formset.is_valid():
            if not ingredient_formset_has_items(ingredient_formset):
                form.add_error(None, 'Add at least one food item to this feed mix.')
            else:
                with transaction.atomic():
                    obj = form.save()
                    save_feed_mix_ingredients(obj, ingredient_formset)
                    write_audit_log(request, AuditLog.CREATE, obj)
                messages.success(request, f'{config["singular"]} created successfully.')
                return redirect('poultry:record_detail', model_slug=model_slug, pk=obj.pk)
        return render(
            request,
            'PoutryManagementSysyem/record_form.html',
            feed_mix_form_context(config, form, ingredient_formset, 'Create'),
        )
    form = Form(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        apply_egg_sale_price(form, model_slug)
        if mobile_money_confirmation_missing(request, model_slug):
            messages.error(request, 'Confirm the Mobile Money payment before saving this egg sale.')
            return render(request, 'PoutryManagementSysyem/record_form.html', record_form_context(config, model_slug, form, 'Create'))
        obj = form.save()
        write_audit_log(request, AuditLog.CREATE, obj)
        messages.success(request, f'{config["singular"]} created successfully.')
        return redirect('poultry:record_detail', model_slug=model_slug, pk=obj.pk)
    return render(request, 'PoutryManagementSysyem/record_form.html', record_form_context(config, model_slug, form, 'Create'))


@login_required
def record_update(request, model_slug, pk):
    config = get_crud_config(model_slug)
    if not config:
        return redirect('poultry:crud_index')
    if config.get('read_only'):
        raise PermissionDenied
    require_model_permission(request, config['model'], 'change')
    obj = get_object_or_404(config['model'], pk=pk)
    Form = build_form_class(config['model'])
    if model_slug == 'feed-mixes':
        form = Form(request.POST or None, instance=obj)
        ingredient_formset = FeedMixIngredientFormSet(
            request.POST or None,
            initial=feed_mix_detail_initial(obj),
            prefix='ingredients',
            feed_mix=obj,
        )
        if request.method == 'POST' and form.is_valid() and ingredient_formset.is_valid():
            if not ingredient_formset_has_items(ingredient_formset):
                form.add_error(None, 'Add at least one food item to this feed mix.')
            else:
                with transaction.atomic():
                    obj = form.save()
                    save_feed_mix_ingredients(obj, ingredient_formset)
                    write_audit_log(request, AuditLog.UPDATE, obj)
                messages.success(request, f'{config["singular"]} updated successfully.')
                return redirect('poultry:record_detail', model_slug=model_slug, pk=obj.pk)
        return render(
            request,
            'PoutryManagementSysyem/record_form.html',
            feed_mix_form_context(config, form, ingredient_formset, 'Edit', obj),
        )
    form = Form(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        apply_egg_sale_price(form, model_slug)
        if mobile_money_confirmation_missing(request, model_slug):
            messages.error(request, 'Confirm the Mobile Money payment before saving this egg sale.')
            return render(request, 'PoutryManagementSysyem/record_form.html', record_form_context(config, model_slug, form, 'Edit', obj))
        obj = form.save()
        write_audit_log(request, AuditLog.UPDATE, obj)
        messages.success(request, f'{config["singular"]} updated successfully.')
        return redirect('poultry:record_detail', model_slug=model_slug, pk=obj.pk)
    return render(request, 'PoutryManagementSysyem/record_form.html', record_form_context(config, model_slug, form, 'Edit', obj))


@login_required
def record_delete(request, model_slug, pk):
    config = get_crud_config(model_slug)
    if not config:
        return redirect('poultry:crud_index')
    if config.get('read_only'):
        raise PermissionDenied
    require_model_permission(request, config['model'], 'delete')
    obj = get_object_or_404(config['model'], pk=pk)
    if request.method == 'POST':
        try:
            object_repr = str(obj)
            object_pk = obj.pk
            obj.delete()
            obj.pk = object_pk
            write_audit_log(request, AuditLog.DELETE, obj, object_repr)
            messages.success(request, f'{config["singular"]} deleted successfully.')
            return redirect('poultry:record_list', model_slug=model_slug)
        except ProtectedError:
            messages.error(request, f'This {config["singular"].lower()} is linked to other records and cannot be deleted.')
            return redirect('poultry:record_detail', model_slug=model_slug, pk=obj.pk)
    return render(request, 'PoutryManagementSysyem/record_confirm_delete.html', {
        'config': config,
        'model_slug': model_slug,
        'object': obj,
    })


@login_required
def dashboard(request):
    period = request.GET.get('period', ProfitSnapshot.DAILY)
    period_labels = dict(ProfitSnapshot.PERIOD_CHOICES)
    valid_periods = set(period_labels)
    if period not in valid_periods:
        period = ProfitSnapshot.DAILY

    report_start = parse_report_date(request.GET.get('start'))
    snapshot = ProfitSnapshot.build_for_period(period, report_start)
    period_range = (snapshot.period_start, snapshot.period_end)

    egg_production = EggProduction.objects.filter(production_date__range=period_range)
    feed_consumption = FeedConsumption.objects.filter(consumption_date__range=period_range)
    egg_sales = EggSale.objects.filter(sale_date__range=period_range)
    purchases = Purchase.objects.filter(purchase_date__range=period_range)
    income = Income.objects.filter(income_date__range=period_range)
    expenses = Expense.objects.filter(expense_date__range=period_range)
    flock_consumption_totals = list(feed_consumption.values(
        'flock_id',
        'flock__breed',
        'flock__house__house_name',
    ).annotate(
        total_quantity=Sum('quantity')
    ).order_by(
        'flock__breed',
        'flock__house__house_name',
    ))
    max_flock_consumption = max(
        (row['total_quantity'] or Decimal('0') for row in flock_consumption_totals),
        default=Decimal('0'),
    )
    flock_feed_consumption = [
        {
            'flock_id': row['flock_id'],
            'flock': f"{row['flock__breed']} - {row['flock__house__house_name']}",
            'house': row['flock__house__house_name'],
            'quantity_display': format_quantity_with_unit(row['total_quantity'] or Decimal('0'), 'kg'),
            'percent': chart_percent(row['total_quantity'], max_flock_consumption),
        }
        for row in flock_consumption_totals
    ]
    feed_usage_by_date = {
        row['consumption_date']: row['total_quantity'] or Decimal('0')
        for row in feed_consumption.values('consumption_date').annotate(total_quantity=Sum('quantity'))
    }
    max_daily_feed = max(feed_usage_by_date.values(), default=Decimal('0'))
    feed_trend = []
    trend_date = snapshot.period_start
    while trend_date <= snapshot.period_end:
        quantity = feed_usage_by_date.get(trend_date, Decimal('0'))
        feed_trend.append({
            'label': trend_date.strftime('%b %d'),
            'quantity_display': format_quantity_with_unit(quantity, 'kg'),
            'percent': chart_percent(quantity, max_daily_feed),
        })
        trend_date += timedelta(days=1)
    finance_values = [
        {'label': 'Egg Sales', 'value': total_for(egg_sales, 'total_amount'), 'class': 'income'},
        {'label': 'Other Income', 'value': total_for(income, 'amount'), 'class': 'income-soft'},
        {'label': 'Purchases', 'value': total_for(purchases, 'total_amount'), 'class': 'expense'},
        {'label': 'Expenses', 'value': total_for(expenses, 'amount'), 'class': 'expense-soft'},
    ]
    max_finance_value = max((row['value'] for row in finance_values), default=Decimal('0'))
    finance_chart = [
        {
            **row,
            'value_display': format_currency(row['value']),
            'percent': chart_percent(row['value'], max_finance_value),
        }
        for row in finance_values
    ]
    dashboard_record_cards = [
        {
            'label': config['title'],
            'slug': slug,
            'value': config['model'].objects.count(),
        }
        for slug, config in CRUD_MODELS.items()
        if has_model_permission(request.user, config['model'], 'view')
    ]

    context = {
        'houses_count': PoultryHouse.objects.count(),
        'active_flocks_count': Flock.objects.filter(remarks=Flock.AVAILABLE).count(),
        'current_birds': total_for(Flock.objects.filter(remarks=Flock.AVAILABLE), 'current_birds'),
        'stock_items_count': InventoryItem.objects.count(),
        'low_stock_notifications': low_stock_notifications(),
        'period_choices': ProfitSnapshot.PERIOD_CHOICES,
        'selected_period': period,
        'selected_period_label': period_labels[period],
        'selected_start': report_start.isoformat(),
        'snapshot': snapshot,
        'eggs_collected': total_for(egg_production, 'eggs_collected'),
        'good_eggs': total_for(egg_production, 'good_eggs'),
        'broken_eggs': total_for(egg_production, 'broken_eggs'),
        'dirty_eggs': total_for(egg_production, 'dirty_eggs'),
        'feed_used': total_for(feed_consumption, 'quantity'),
        'flock_feed_consumption': flock_feed_consumption,
        'feed_trend': feed_trend,
        'finance_chart': finance_chart,
        'dashboard_record_cards': dashboard_record_cards,
        'egg_sales_total': total_for(egg_sales, 'total_amount'),
        'purchases_total': total_for(purchases, 'total_amount'),
        'other_income_total': total_for(income, 'amount'),
        'expenses_total': total_for(expenses, 'amount'),
        'dashboard_links': [
            {'label': 'Poultry Houses', 'slug': 'houses'},
            {'label': 'Flocks', 'slug': 'flocks'},
            {'label': 'Purchases', 'slug': 'purchases'},
            {'label': 'Feed Mixes', 'slug': 'feed-mixes'},
            {'label': 'Feed Mixing Details', 'slug': 'feed-mix-details'},
            {'label': 'Feed Consumption', 'slug': 'feed-consumption'},
            {'label': 'Egg Production', 'slug': 'egg-production'},
            {'label': 'Egg Prices', 'slug': 'egg-prices'},
            {'label': 'Egg Sales', 'slug': 'egg-sales'},
            {'label': 'Expenses', 'slug': 'expenses'},
            {'label': 'Income', 'slug': 'income'},
            {'label': 'Audit Logs', 'slug': 'audit-logs'},
        ],
    }
    return render(request, 'PoutryManagementSysyem/dashboard.html', context)
