from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from .models import AuditLog, EggPrice, EggProduction, EggSale, FeedConsumption, FeedMix, FeedMixDetail, Flock, InventoryItem, PoultryHouse, Purchase


class AuthenticatedTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(
            username='admin',
            email='admin@example.com',
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.user)


class CrudViewTests(AuthenticatedTestCase):
    def test_dashboard_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse('poultry:dashboard'))

        self.assertRedirects(response, f'{reverse("login")}?next={reverse("poultry:dashboard")}')

    def test_crud_index_loads(self):
        response = self.client.get(reverse('poultry:crud_index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Farm Records')
        self.assertContains(response, 'Poultry Houses')
        self.assertNotContains(response, 'Inventory')

    def test_inventory_records_route_is_removed(self):
        response = self.client.get(reverse('poultry:record_list', args=['inventory']))

        self.assertRedirects(response, reverse('poultry:crud_index'))

    def test_can_create_update_and_delete_house(self):
        create_response = self.client.post(reverse('poultry:record_create', args=['houses']), {
            'house_name': 'Layer House A',
            'capacity': 500,
            'bird_type': PoultryHouse.LAYER,
            'status': PoultryHouse.ACTIVE,
        })
        house = PoultryHouse.objects.get(house_name='Layer House A')

        self.assertRedirects(create_response, reverse('poultry:record_detail', args=['houses', house.pk]))

        update_response = self.client.post(reverse('poultry:record_update', args=['houses', house.pk]), {
            'house_name': 'Layer House A',
            'capacity': 650,
            'bird_type': PoultryHouse.LAYER,
            'status': PoultryHouse.MAINTENANCE,
        })
        house.refresh_from_db()

        self.assertRedirects(update_response, reverse('poultry:record_detail', args=['houses', house.pk]))
        self.assertEqual(house.capacity, 650)
        self.assertEqual(house.status, PoultryHouse.MAINTENANCE)

        delete_response = self.client.post(reverse('poultry:record_delete', args=['houses', house.pk]))

        self.assertRedirects(delete_response, reverse('poultry:record_list', args=['houses']))
        self.assertFalse(PoultryHouse.objects.filter(pk=house.pk).exists())
        self.assertEqual(AuditLog.objects.filter(action=AuditLog.CREATE).count(), 1)
        self.assertEqual(AuditLog.objects.filter(action=AuditLog.UPDATE).count(), 1)
        self.assertEqual(AuditLog.objects.filter(action=AuditLog.DELETE).count(), 1)
        self.assertTrue(AuditLog.objects.filter(user=self.user, model_label='PoutryManagementSysyem.PoultryHouse').exists())

    def test_user_without_add_permission_cannot_create_record(self):
        limited_user = get_user_model().objects.create_user(
            username='viewer',
            email='viewer@example.com',
            password='password',
        )
        self.client.force_login(limited_user)

        response = self.client.post(reverse('poultry:record_create', args=['houses']), {
            'house_name': 'Restricted House',
            'capacity': 500,
            'bird_type': PoultryHouse.LAYER,
            'status': PoultryHouse.ACTIVE,
        })

        self.assertEqual(response.status_code, 403)
        self.assertFalse(PoultryHouse.objects.filter(house_name='Restricted House').exists())

    def test_can_create_role_with_permissions(self):
        permission = Permission.objects.get(codename='view_poultryhouse')

        response = self.client.post(reverse('poultry:role_create'), {
            'name': 'Viewer',
            'permissions': [str(permission.pk)],
        })

        role = Group.objects.get(name='Viewer')
        self.assertRedirects(response, reverse('poultry:role_list'))
        self.assertTrue(role.permissions.filter(pk=permission.pk).exists())
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.CREATE, model_label='auth.Group').exists())

    def test_can_add_user_and_assign_role(self):
        role = Group.objects.create(name='Farm Manager')

        response = self.client.post(reverse('poultry:user_create'), {
            'username': 'manager',
            'email': 'manager@example.com',
            'first_name': 'Farm',
            'last_name': 'Manager',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
            'groups': [str(role.pk)],
        })

        user = get_user_model().objects.get(username='manager')
        self.assertRedirects(response, reverse('poultry:user_list'))
        self.assertEqual(user.email, 'manager@example.com')
        self.assertTrue(user.groups.filter(pk=role.pk).exists())
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.CREATE, model_label=user._meta.label).exists())

    def test_can_update_user_roles(self):
        viewer = Group.objects.create(name='Viewer')
        manager = Group.objects.create(name='Manager')
        user = get_user_model().objects.create_user(username='staff', password='password')
        user.groups.add(viewer)

        response = self.client.post(reverse('poultry:user_assign_roles', args=[user.pk]), {
            'groups': [str(manager.pk)],
        })

        user.refresh_from_db()
        self.assertRedirects(response, reverse('poultry:user_list'))
        self.assertFalse(user.groups.filter(pk=viewer.pk).exists())
        self.assertTrue(user.groups.filter(pk=manager.pk).exists())

    def test_egg_sale_form_has_mobile_money_prompt(self):
        response = self.client.get(reverse('poultry:record_create', args=['egg-sales']))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mobile Money')
        self.assertContains(response, 'data-payment-modal')
        self.assertContains(response, 'Amount to pay')

    def test_flock_breed_is_selection_field(self):
        response = self.client.get(reverse('poultry:record_create', args=['flocks']))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="breed"')
        self.assertContains(response, 'name="remarks"')
        self.assertContains(response, 'ISA Brown')
        self.assertContains(response, 'Lohmann Brown')
        self.assertContains(response, 'Cobb 500')
        self.assertContains(response, 'Died')
        self.assertContains(response, 'Sick')
        self.assertContains(response, 'Available')

    def test_poultry_house_status_uses_capacity_options(self):
        response = self.client.get(reverse('poultry:record_create', args=['houses']))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Full capacity')
        self.assertContains(response, 'Half capacity')
        self.assertContains(response, 'Empty')
        self.assertNotContains(response, 'Maintenance')

    def test_dashboard_links_to_record_tables(self):
        response = self.client.get(reverse('poultry:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Daily Summary')
        self.assertContains(response, 'All Records')
        self.assertContains(response, 'Egg Sales')
        self.assertContains(response, 'Purchases')
        self.assertContains(response, 'Other Income')
        self.assertContains(response, 'Expenses Paid')
        for slug in [
            'houses',
            'flocks',
            'purchases',
            'feed-mixes',
            'feed-mix-details',
            'feed-consumption',
            'egg-production',
            'egg-prices',
            'egg-sales',
            'expenses',
            'income',
            'audit-logs',
        ]:
            self.assertContains(response, reverse('poultry:record_list', args=[slug]))
        self.assertNotContains(response, 'Recent')

    def test_dashboard_record_cards_show_live_record_counts(self):
        PoultryHouse.objects.create(
            house_name='Dashboard House',
            capacity=250,
            bird_type=PoultryHouse.LAYER,
            status=PoultryHouse.ACTIVE,
        )
        Purchase.objects.create(
            item_name='Dashboard Feed',
            category='Feed',
            quantity=Decimal('10.00'),
            unit_price=Decimal('2000.00'),
        )

        response = self.client.get(reverse('poultry:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Poultry Houses')
        self.assertContains(response, 'Purchases')
        self.assertContains(response, reverse('poultry:record_list', args=['houses']))
        self.assertContains(response, reverse('poultry:record_list', args=['purchases']))

    def test_dashboard_shows_daily_feed_consumption_by_flock(self):
        house = PoultryHouse.objects.create(
            house_name='Layer House Feed',
            capacity=500,
            bird_type=PoultryHouse.LAYER,
            status=PoultryHouse.ACTIVE,
        )
        flock = Flock.objects.create(
            house=house,
            breed=Flock.ISA_BROWN,
            purchase_date='2026-06-28',
            number_of_birds=200,
            cost_per_bird=Decimal('12000.00'),
            current_birds=200,
            remarks=Flock.AVAILABLE,
        )
        feed_mix = FeedMix.objects.create(
            mix_name=FeedMix.LAYER_FORMULA,
            mixing_date='2026-06-28',
            stock=Decimal('20.00'),
        )
        FeedConsumption.objects.create(
            flock=flock,
            feed_mix=feed_mix,
            consumption_date='2026-06-28',
            quantity=Decimal('7.50'),
            issued_by='Farm Manager',
        )
        FeedConsumption.objects.create(
            flock=flock,
            feed_mix=feed_mix,
            consumption_date='2026-06-28',
            quantity=Decimal('2.50'),
            issued_by='Farm Manager',
        )

        response = self.client.get(reverse('poultry:dashboard'), {
            'period': 'Daily',
            'start': '2026-06-28',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Daily Consumption By Flock')
        self.assertContains(response, 'ISA Brown - Layer House Feed')
        self.assertContains(response, '10kgs')

    def test_flock_table_shows_balance(self):
        house = PoultryHouse.objects.create(
            house_name='Layer House C',
            capacity=300,
            bird_type=PoultryHouse.LAYER,
            status=PoultryHouse.ACTIVE,
        )
        flock = Flock.objects.create(
            house=house,
            breed=Flock.LOCAL,
            number_of_birds=100,
            cost_per_bird=Decimal('10000.00'),
            current_birds=82,
            remarks=Flock.DIED,
        )

        response = self.client.get(reverse('poultry:record_list', args=['flocks']))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Balance')
        self.assertContains(response, 'Number Of Birds Purchased')
        self.assertContains(response, '18')
        self.assertContains(response, '18 Died')
        self.assertEqual(flock.balance, 18)
        self.assertEqual(flock.remarks_status, '18 Died')

    def test_mobile_money_egg_sale_requires_confirmation(self):
        house = PoultryHouse.objects.create(
            house_name='Mobile Money House',
            capacity=300,
            bird_type=PoultryHouse.LAYER,
            status=PoultryHouse.ACTIVE,
        )
        flock = Flock.objects.create(
            house=house,
            breed=Flock.LOCAL,
            number_of_birds=100,
            cost_per_bird=Decimal('10000.00'),
            current_birds=100,
        )
        production = EggProduction.objects.create(
            flock=flock,
            production_date='2026-06-28',
            eggs_collected=100,
            broken_eggs=0,
            dirty_eggs=0,
        )
        payload = {
            'egg_production': production.pk,
            'sale_date': '2026-06-28',
            'sale_type': EggSale.TRAY,
            'quantity': '2.00',
            'rate': '15000.00',
            'payment_method': 'Mobile Money',
        }

        response = self.client.post(reverse('poultry:record_create', args=['egg-sales']), payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Confirm the Mobile Money payment')
        self.assertFalse(EggSale.objects.exists())

        confirmed_payload = {
            **payload,
            'mobile_money_confirmed': '1',
            'mobile_money_number': '0700000000',
            'mobile_money_request_id': 'MM-TEST-123',
        }
        confirmed_response = self.client.post(reverse('poultry:record_create', args=['egg-sales']), confirmed_payload)

        sale = EggSale.objects.get()
        self.assertRedirects(confirmed_response, reverse('poultry:record_detail', args=['egg-sales', sale.pk]))
        self.assertEqual(sale.total_amount, Decimal('30000.0000'))

    def test_mobile_money_payment_request_endpoint(self):
        response = self.client.post(reverse('poultry:request_mobile_money_payment'), {
            'provider': 'simulator',
            'mobile_number': '0700000000',
            'amount': '30000.00',
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['status'], 'approval_sent')
        self.assertTrue(data['simulated'])
        self.assertIn('No PIN prompt', data['message'])
        self.assertTrue(data['transaction_id'].startswith('SIMULATOR-'))
        status_response = self.client.get(reverse('poultry:mobile_money_payment_status', args=[data['transaction_id']]))
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()['status'], 'approved')

    def test_mobile_money_providers_endpoint(self):
        response = self.client.get(reverse('poultry:mobile_money_providers'))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        providers = {provider['code']: provider for provider in data['providers']}
        self.assertIn('simulator', providers)
        self.assertTrue(providers['simulator']['simulated'])
        self.assertIn('mtn', providers)
        self.assertIn('airtel', providers)

    def test_mobile_money_payment_request_rejects_unconfigured_provider(self):
        response = self.client.post(reverse('poultry:request_mobile_money_payment'), {
            'provider': 'mtn',
            'mobile_number': '0770000000',
            'amount': '30000.00',
        })

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['ok'])

    def test_mobile_money_payment_request_requires_amount(self):
        response = self.client.post(reverse('poultry:request_mobile_money_payment'), {
            'mobile_number': '0700000000',
            'amount': '0',
        })

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['ok'])

    def test_egg_sale_rate_is_selected_from_egg_price(self):
        house = PoultryHouse.objects.create(
            house_name='Layer House B',
            capacity=300,
            bird_type=PoultryHouse.LAYER,
            status=PoultryHouse.ACTIVE,
        )
        flock = Flock.objects.create(
            house=house,
            breed='Lohmann Brown',
            number_of_birds=120,
            cost_per_bird=Decimal('12000.00'),
            current_birds=120,
        )
        production = EggProduction.objects.create(
            flock=flock,
            production_date='2026-06-28',
            eggs_collected=120,
            broken_eggs=2,
            dirty_eggs=3,
        )
        price = EggPrice.objects.create(
            sale_type=EggSale.TRAY,
            rate=Decimal('18000.00'),
            is_active=True,
        )

        form_response = self.client.get(reverse('poultry:record_create', args=['egg-sales']))

        self.assertContains(form_response, 'Egg production')
        self.assertContains(form_response, 'Egg price')
        self.assertContains(form_response, str(production))
        self.assertContains(form_response, str(price))
        self.assertContains(form_response, 'egg-price-rates')

        create_response = self.client.post(reverse('poultry:record_create', args=['egg-sales']), {
            'egg_production': production.pk,
            'egg_price': price.pk,
            'sale_date': '2026-06-28',
            'sale_type': EggSale.EGG,
            'quantity': '3.00',
            'rate': '15000.00',
            'payment_method': 'Cash',
        })

        sale = EggSale.objects.get(egg_production=production)
        self.assertRedirects(create_response, reverse('poultry:record_detail', args=['egg-sales', sale.pk]))
        self.assertEqual(sale.quantity, Decimal('3.00'))
        self.assertEqual(sale.rate, Decimal('18000.00'))
        self.assertEqual(sale.sale_type, EggSale.TRAY)
        self.assertEqual(sale.total_amount, Decimal('54000.0000'))

    def test_egg_sale_cannot_exceed_available_good_eggs(self):
        # Arrange
        house = PoultryHouse.objects.create(
            house_name='Egg Control House',
            capacity=200,
            bird_type=PoultryHouse.LAYER,
            status=PoultryHouse.ACTIVE,
        )
        flock = Flock.objects.create(
            house=house,
            breed=Flock.ISA_BROWN,
            number_of_birds=80,
            cost_per_bird=Decimal('12000.00'),
            current_birds=80,
        )
        production = EggProduction.objects.create(
            flock=flock,
            production_date='2026-06-28',
            eggs_collected=40,
            broken_eggs=5,
            dirty_eggs=5,
        )

        # Act
        response = self.client.post(reverse('poultry:record_create', args=['egg-sales']), {
            'egg_production': production.pk,
            'sale_date': '2026-06-28',
            'sale_type': EggSale.TRAY,
            'quantity': '2.00',
            'rate': '15000.00',
            'payment_method': 'Cash',
        })

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'cannot exceed available good eggs')
        self.assertFalse(EggSale.objects.exists())

    def test_egg_sales_table_hides_source_record_columns(self):
        # Act
        response = self.client.get(reverse('poultry:record_list', args=['egg-sales']))

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Egg production')
        self.assertNotContains(response, 'Egg price')

    def test_dashboard_shows_low_egg_stock_notification(self):
        # Arrange
        house = PoultryHouse.objects.create(
            house_name='Egg Alert House',
            capacity=200,
            bird_type=PoultryHouse.LAYER,
            status=PoultryHouse.ACTIVE,
        )
        flock = Flock.objects.create(
            house=house,
            breed=Flock.LOCAL,
            number_of_birds=80,
            cost_per_bird=Decimal('12000.00'),
            current_birds=80,
        )
        production = EggProduction.objects.create(
            flock=flock,
            production_date='2026-06-28',
            eggs_collected=150,
            broken_eggs=0,
            dirty_eggs=0,
        )
        EggSale.objects.create(
            egg_production=production,
            sale_date='2026-06-28',
            sale_type=EggSale.TRAY,
            quantity=Decimal('4.00'),
            rate=Decimal('15000.00'),
            payment_method='Cash',
        )

        # Act
        response = self.client.get(reverse('poultry:dashboard'))

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Egg tray balance is low at 1 trays.')
        self.assertContains(response, 'Loose egg balance is low at 0 eggs.')

    def test_egg_production_shows_balances_after_sale_update(self):
        # Arrange
        house = PoultryHouse.objects.create(
            house_name='Egg Balance House',
            capacity=200,
            bird_type=PoultryHouse.LAYER,
            status=PoultryHouse.ACTIVE,
        )
        flock = Flock.objects.create(
            house=house,
            breed=Flock.LOCAL,
            number_of_birds=80,
            cost_per_bird=Decimal('12000.00'),
            current_birds=80,
        )
        production = EggProduction.objects.create(
            flock=flock,
            production_date='2026-06-28',
            eggs_collected=124,
            broken_eggs=2,
            dirty_eggs=2,
        )
        sale = EggSale.objects.create(
            egg_production=production,
            sale_date='2026-06-28',
            sale_type=EggSale.TRAY,
            quantity=Decimal('2.00'),
            rate=Decimal('15000.00'),
            payment_method='Cash',
        )

        # Act
        response = self.client.get(reverse('poultry:record_list', args=['egg-production']))

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Egg Balance')
        self.assertContains(response, 'Tray Balance')
        self.assertContains(response, '60 eggs')
        self.assertContains(response, '2 trays')
        self.assertEqual(production.sold_eggs, Decimal('60.00'))
        self.assertEqual(production.egg_balance, Decimal('60.00'))
        self.assertEqual(production.tray_balance, Decimal('2'))

        sale.quantity = Decimal('3.00')
        sale.save()

        # Act
        detail_response = self.client.get(reverse('poultry:record_detail', args=['egg-production', production.pk]))

        # Assert
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, 'Sold Eggs')
        self.assertContains(detail_response, '90 eggs')
        self.assertContains(detail_response, '30 eggs')
        self.assertContains(detail_response, '1 trays')
        self.assertContains(detail_response, '0 eggs')


class PurchaseInventorySyncTests(AuthenticatedTestCase):
    def test_purchase_creates_inventory_item_and_adds_stock(self):
        purchase = Purchase.objects.create(
            item_name='Layer Mash',
            category='Feed',
            quantity=Decimal('25.00'),
            unit='kg',
            reorder_level=Decimal('5.00'),
            unit_price=Decimal('2000.00'),
        )

        item = InventoryItem.objects.get(item_name='Layer Mash')
        self.assertEqual(item.category, 'Feeds')
        self.assertEqual(item.unit, 'kg')
        self.assertEqual(item.current_stock, Decimal('25.00'))
        self.assertEqual(item.reorder_level, Decimal('5.00'))
        self.assertEqual(purchase.stock_balance, Decimal('25.00'))

    def test_purchase_reuses_existing_inventory_item(self):
        InventoryItem.objects.create(item_name='Grower Mash', category='Feed', unit='kg', reorder_level=Decimal('3.00'))

        Purchase.objects.create(
            item_name='Grower Mash',
            category='Feed',
            quantity=Decimal('10.00'),
            unit='kg',
            reorder_level=Decimal('4.00'),
            unit_price=Decimal('1800.00'),
        )
        Purchase.objects.create(
            item_name='Grower Mash',
            category='Feed',
            quantity=Decimal('15.00'),
            unit='kg',
            reorder_level=Decimal('7.00'),
            unit_price=Decimal('1800.00'),
        )

        item = InventoryItem.objects.get(item_name='Grower Mash')
        self.assertEqual(item.current_stock, Decimal('25.00'))
        self.assertEqual(item.reorder_level, Decimal('7.00'))

    def test_purchase_table_formats_quantity_and_money_without_reorder_level(self):
        Purchase.objects.create(
            item_name='Vitamin Premix',
            category='Supplements',
            quantity=Decimal('12.00'),
            unit='kg',
            reorder_level=Decimal('1.00'),
            unit_price=Decimal('5000.00'),
        )

        response = self.client.get(reverse('poultry:record_list', args=['purchases']))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Reorder Level')
        self.assertContains(response, 'Stock Balance')
        self.assertContains(response, '12kgs')
        self.assertContains(response, 'UGX 5,000')
        self.assertContains(response, 'UGX 60,000')

    def test_purchase_form_hides_internal_inventory_item_field(self):
        response = self.client.get(reverse('poultry:record_create', args=['purchases']))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Inventory item')
        self.assertNotContains(response, 'name="unit"')
        self.assertContains(response, 'Item name')
        self.assertContains(response, 'name="item_name"')
        self.assertContains(response, 'Layer Mash')
        self.assertContains(response, 'Cotton Cake')
        self.assertContains(response, 'Soybean Meal')
        self.assertContains(response, 'Wheat Bran')
        self.assertContains(response, 'Oyster Shell')
        self.assertContains(response, 'Methionine')
        self.assertContains(response, 'name="category"')
        self.assertContains(response, 'Feed Ingredients')
        self.assertContains(response, 'purchase-item-categories')

    def test_purchase_generates_unit_from_category_and_item(self):
        feed_purchase = Purchase.objects.create(
            item_name='Layer Mash',
            category='Feeds',
            quantity=Decimal('10.00'),
            reorder_level=Decimal('2.00'),
            unit_price=Decimal('1800.00'),
        )
        stationery_purchase = Purchase.objects.create(
            item_name='Receipt Book',
            category='Stationery',
            quantity=Decimal('4.00'),
            reorder_level=Decimal('1.00'),
            unit_price=Decimal('3000.00'),
        )
        medicine_purchase = Purchase.objects.create(
            item_name='Newcastle Vaccine',
            category='Medicine',
            quantity=Decimal('2.00'),
            reorder_level=Decimal('1.00'),
            unit_price=Decimal('8000.00'),
        )

        self.assertEqual(feed_purchase.unit, 'kg')
        self.assertEqual(stationery_purchase.unit, 'pc')
        self.assertEqual(medicine_purchase.unit, 'bottle')
        self.assertEqual(InventoryItem.objects.get(item_name='Layer Mash').unit, 'kg')
        self.assertEqual(InventoryItem.objects.get(item_name='Receipt Book').unit, 'pc')
        self.assertEqual(InventoryItem.objects.get(item_name='Newcastle Vaccine').unit, 'bottle')

    def test_purchase_form_maps_generated_poultry_feeds_to_categories(self):
        ingredient_purchase = Purchase.objects.create(
            item_name='Soybean Meal',
            category='Other',
            quantity=Decimal('20.00'),
            reorder_level=Decimal('5.00'),
            unit_price=Decimal('2500.00'),
        )
        supplement_purchase = Purchase.objects.create(
            item_name='Methionine',
            category='Other',
            quantity=Decimal('3.00'),
            reorder_level=Decimal('1.00'),
            unit_price=Decimal('9000.00'),
        )

        self.assertEqual(ingredient_purchase.category, 'Feed Ingredients')
        self.assertEqual(supplement_purchase.category, 'Supplements')
        self.assertEqual(ingredient_purchase.unit, 'kg')
        self.assertEqual(supplement_purchase.unit, 'kg')

    def test_dashboard_shows_low_stock_reorder_notification(self):
        Purchase.objects.create(
            item_name='Layer Mash',
            category='Feeds',
            quantity=Decimal('12.00'),
            reorder_level=Decimal('20.00'),
            unit_price=Decimal('1800.00'),
        )

        response = self.client.get(reverse('poultry:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Low Stock Notifications')
        self.assertContains(response, 'Layer Mash')
        self.assertContains(response, 'Balance: 12kgs')
        self.assertContains(response, 'Layer Mash balance is low at 12kgs. Layer Mash needs refill.')

    def test_purchase_update_and_delete_adjust_inventory_stock(self):
        purchase = Purchase.objects.create(
            item_name='Starter Feed',
            category='Feed',
            quantity=Decimal('12.00'),
            unit='kg',
            unit_price=Decimal('2200.00'),
        )

        purchase.quantity = Decimal('8.00')
        purchase.save()
        item = InventoryItem.objects.get(item_name='Starter Feed')
        purchase.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal('8.00'))
        self.assertEqual(purchase.stock_balance, Decimal('8.00'))

        purchase.delete()
        item.refresh_from_db()
        self.assertEqual(item.current_stock, Decimal('0.00'))


class FeedMixCalculationTests(AuthenticatedTestCase):
    def feed_mix_post_data(self, mix_name, ingredient_rows):
        data = {
            'mix_name': mix_name,
            'mixing_date': '2026-06-28',
            'ingredients-TOTAL_FORMS': str(max(len(ingredient_rows), 1)),
            'ingredients-INITIAL_FORMS': '0',
            'ingredients-MIN_NUM_FORMS': '0',
            'ingredients-MAX_NUM_FORMS': '1000',
        }
        for index, (purchase, quantity) in enumerate(ingredient_rows):
            data[f'ingredients-{index}-purchase'] = str(purchase.pk)
            data[f'ingredients-{index}-quantity'] = str(quantity)
        return data

    def test_feed_mix_totals_and_price_per_kg(self):
        maize = InventoryItem.objects.create(
            item_name='Maize Bran',
            category='Feed',
            unit='kg',
            current_stock=Decimal('100.00'),
        )
        concentrate = InventoryItem.objects.create(
            item_name='Concentrate',
            category='Feed',
            unit='kg',
            current_stock=Decimal('100.00'),
        )
        feed_mix = FeedMix.objects.create(mix_name='Layer Formula')

        FeedMixDetail.objects.create(
            feed_mix=feed_mix,
            inventory_item=maize,
            quantity=Decimal('20.00'),
            unit_price=Decimal('1500.00'),
        )
        FeedMixDetail.objects.create(
            feed_mix=feed_mix,
            inventory_item=concentrate,
            quantity=Decimal('5.00'),
            unit_price=Decimal('7000.00'),
        )

        self.assertEqual(feed_mix.total_quantity, Decimal('25.00'))
        self.assertEqual(feed_mix.total_unit_price, Decimal('8500.00'))
        self.assertEqual(feed_mix.total_cost, Decimal('65000.00'))
        self.assertEqual(feed_mix.price_per_kg, Decimal('2600.00'))

    def test_feed_mix_price_per_kg_is_zero_without_details(self):
        feed_mix = FeedMix.objects.create(mix_name='Empty Formula')

        self.assertEqual(feed_mix.total_quantity, Decimal('0'))
        self.assertEqual(feed_mix.total_unit_price, Decimal('0'))
        self.assertEqual(feed_mix.total_cost, Decimal('0'))
        self.assertEqual(feed_mix.price_per_kg, Decimal('0'))

    def test_feed_mix_form_captures_table_fields_and_calculates_total_amount(self):
        maize = Purchase.objects.create(
            item_name='Maize Bran',
            category='Feed Ingredients',
            quantity=Decimal('30.00'),
            reorder_level=Decimal('5.00'),
            unit_price=Decimal('1400.00'),
        )
        soya = Purchase.objects.create(
            item_name='Soya',
            category='Feed Ingredients',
            quantity=Decimal('20.00'),
            reorder_level=Decimal('5.00'),
            unit_price=Decimal('2500.00'),
        )

        response = self.client.post(
            reverse('poultry:record_create', args=['feed-mixes']),
            self.feed_mix_post_data(FeedMix.LAYER_FORMULA, [(maize, '12.00'), (soya, '3.00')]),
        )

        feed_mix = FeedMix.objects.get(mix_name=FeedMix.LAYER_FORMULA)
        self.assertRedirects(response, reverse('poultry:record_detail', args=['feed-mixes', feed_mix.pk]))
        self.assertEqual(feed_mix.item_name, 'Maize Bran')
        self.assertEqual(feed_mix.details.count(), 2)
        self.assertEqual(feed_mix.quantity, Decimal('15.00'))
        self.assertEqual(feed_mix.stock, Decimal('15.00'))
        self.assertEqual(feed_mix.unit_price, Decimal('3900.00'))
        self.assertEqual(feed_mix.total_amount, Decimal('24300.0000'))
        self.assertEqual(feed_mix.price_per_kg, Decimal('1620.00'))
        maize.refresh_from_db()
        soya.refresh_from_db()
        self.assertEqual(maize.stock_balance, Decimal('18.00'))
        self.assertEqual(soya.stock_balance, Decimal('17.00'))

    def test_feed_mix_form_allows_item_name_from_purchase_table(self):
        pen = Purchase.objects.create(
            item_name='Pen',
            category='Stationery',
            quantity=Decimal('10.00'),
            reorder_level=Decimal('2.00'),
            unit_price=Decimal('500.00'),
        )

        response = self.client.post(
            reverse('poultry:record_create', args=['feed-mixes']),
            self.feed_mix_post_data(FeedMix.LAYER_FORMULA, [(pen, '8.00')]),
        )

        feed_mix = FeedMix.objects.get(mix_name=FeedMix.LAYER_FORMULA)
        self.assertRedirects(response, reverse('poultry:record_detail', args=['feed-mixes', feed_mix.pk]))
        self.assertEqual(feed_mix.item_name, 'Pen')
        self.assertEqual(feed_mix.unit_price, Decimal('500.00'))

    def test_feed_mix_form_rejects_quantity_greater_than_purchase_quantity(self):
        purchase = Purchase.objects.create(
            item_name='Grower Mash',
            category='Feeds',
            quantity=Decimal('10.00'),
            reorder_level=Decimal('2.00'),
            unit_price=Decimal('7000.00'),
        )

        response = self.client.post(
            reverse('poultry:record_create', args=['feed-mixes']),
            self.feed_mix_post_data(FeedMix.GROWER_MASH, [(purchase, '12.00')]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Grower Mash feed mix quantity (12kg) cannot exceed purchase stock balance (10kg).')
        self.assertFalse(FeedMix.objects.exists())

    def test_feed_mix_form_requires_at_least_one_food_item(self):
        response = self.client.post(
            reverse('poultry:record_create', args=['feed-mixes']),
            self.feed_mix_post_data(FeedMix.LAYER_FORMULA, []),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Add at least one food item to this feed mix.')
        self.assertFalse(FeedMix.objects.exists())

    def test_feed_mix_detail_page_hides_internal_fields_and_uses_compact_layout(self):
        feed_mix = FeedMix.objects.create(
            mix_name=FeedMix.PROTEIN_MIX,
            item_name='Soya',
            quantity=Decimal('5.00'),
            unit_price=Decimal('3000.00'),
            remarks='Internal note',
        )

        response = self.client.get(reverse('poultry:record_detail', args=['feed-mixes', feed_mix.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'detail-panel-feed-mixes')
        self.assertContains(response, 'Mix Name')
        self.assertContains(response, 'Protein Mix')
        self.assertContains(response, '5kgs')
        self.assertContains(response, 'UGX 3,000')
        self.assertContains(response, 'UGX 15,000')
        self.assertContains(response, 'Stock')
        self.assertNotContains(response, 'Item Name')
        self.assertNotContains(response, 'Purchased Item')
        self.assertNotContains(response, 'Remarks')
        self.assertNotContains(response, 'Internal note')

    def test_feed_mix_list_shows_table_and_summary_calculations(self):
        item = InventoryItem.objects.create(
            item_name='Soya',
            category='Feed',
            unit='kg',
            current_stock=Decimal('50.00'),
        )
        feed_mix = FeedMix.objects.create(mix_name='Protein Mix')
        FeedMixDetail.objects.create(
            feed_mix=feed_mix,
            inventory_item=item,
            quantity=Decimal('10.00'),
            unit_price=Decimal('3000.00'),
        )

        response = self.client.get(reverse('poultry:record_list', args=['feed-mixes']))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Quantity')
        self.assertContains(response, 'Unit Price')
        self.assertContains(response, 'Total Amount')
        self.assertContains(response, 'Stock')
        self.assertContains(response, 'Totals')
        self.assertNotContains(response, 'Total quantity of mixed feeds')
        self.assertContains(response, '10kgs')
        self.assertContains(response, 'UGX 30,000')
        self.assertContains(response, 'UGX 3,000')

    def test_feed_mix_form_uses_generated_mix_name_dropdown(self):
        purchase = Purchase.objects.create(
            item_name='Maize Bran',
            category='Feeds',
            quantity=Decimal('30.00'),
            reorder_level=Decimal('5.00'),
            unit_price=Decimal('1400.00'),
        )

        response = self.client.get(reverse('poultry:record_create', args=['feed-mixes']))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="mix_name"')
        self.assertContains(response, 'name="ingredients-0-purchase"')
        self.assertContains(response, 'name="ingredients-0-quantity"')
        self.assertContains(response, 'name="ingredients-TOTAL_FORMS" value="1"')
        self.assertNotContains(response, 'name="ingredients-1-purchase"')
        self.assertContains(response, 'name="mixing_date"')
        self.assertNotContains(response, 'name="item_name"')
        self.assertNotContains(response, 'name="quantity"')
        self.assertNotContains(response, 'name="unit_price"')
        self.assertNotContains(response, 'name="total_amount"')
        self.assertNotContains(response, 'name="remarks"')
        self.assertContains(response, 'Layer Formula')
        self.assertContains(response, 'Broiler Finisher')
        self.assertContains(response, 'Grower Mash')
        self.assertContains(response, 'Maize Bran')
        self.assertContains(response, 'feed-mix-purchase-prices')
        self.assertContains(response, 'feed-mix-recipe-purchase-options')
        self.assertContains(response, '1400.00')
        self.assertContains(response, 'Stock')
        self.assertContains(response, 'Add food')
        self.assertNotContains(response, '<option value="Soya">Soya</option>', html=True)
        self.assertNotContains(response, 'Purchased Item')
        self.assertNotContains(response, 'feed-item-prices')
        self.assertContains(response, '30kgs')

    def test_feed_mix_form_only_displays_items_available_in_purchases(self):
        Purchase.objects.create(
            item_name='Soya',
            category='Feed Ingredients',
            quantity=Decimal('30.00'),
            reorder_level=Decimal('5.00'),
            unit_price=Decimal('2500.00'),
        )

        response = self.client.get(reverse('poultry:record_create', args=['feed-mixes']))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<option value="1">Soya</option>', html=True)
        self.assertNotContains(response, 'Maize Bran')
        self.assertContains(response, '"Soya"')
        self.assertContains(response, '2500.00')

    def test_feed_mix_table_shows_recipe_totals_without_single_purchase(self):
        purchase = Purchase.objects.create(
            item_name='Soya',
            category='Feeds',
            quantity=Decimal('15.00'),
            reorder_level=Decimal('4.00'),
            unit_price=Decimal('3000.00'),
        )
        feed_mix = FeedMix.objects.create(mix_name='Protein Mix')
        FeedMixDetail.objects.create(
            feed_mix=feed_mix,
            purchase=purchase,
            inventory_item=purchase.inventory_item,
            quantity=Decimal('5.00'),
            unit_price=Decimal('3000.00'),
        )

        response = self.client.get(reverse('poultry:record_list', args=['feed-mixes']))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Purchased Item')
        self.assertContains(response, '5kgs')
        self.assertContains(response, 'UGX 15,000')

    def test_feed_consumption_reduces_feed_mix_stock(self):
        house = PoultryHouse.objects.create(
            house_name='Layer House Stock',
            capacity=300,
            bird_type=PoultryHouse.LAYER,
            status=PoultryHouse.ACTIVE,
        )
        flock = Flock.objects.create(
            house=house,
            breed=Flock.ISA_BROWN,
            number_of_birds=100,
            current_birds=100,
            cost_per_bird=Decimal('12000.00'),
        )
        feed_mix = FeedMix.objects.create(
            mix_name=FeedMix.LAYER_FORMULA,
            quantity=Decimal('25.00'),
            stock=Decimal('25.00'),
        )

        consumption = FeedConsumption.objects.create(
            flock=flock,
            feed_mix=feed_mix,
            quantity=Decimal('7.00'),
            issued_by='Store',
        )
        feed_mix.refresh_from_db()
        self.assertEqual(feed_mix.stock, Decimal('18.00'))

        consumption.quantity = Decimal('5.00')
        consumption.save()
        feed_mix.refresh_from_db()
        self.assertEqual(feed_mix.stock, Decimal('20.00'))

        consumption.delete()
        feed_mix.refresh_from_db()
        self.assertEqual(feed_mix.stock, Decimal('25.00'))

    def test_feed_consumption_form_rejects_quantity_above_feed_mix_stock(self):
        house = PoultryHouse.objects.create(
            house_name='Layer House Stock Limit',
            capacity=300,
            bird_type=PoultryHouse.LAYER,
            status=PoultryHouse.ACTIVE,
        )
        flock = Flock.objects.create(
            house=house,
            breed=Flock.ISA_BROWN,
            number_of_birds=100,
            current_birds=100,
            cost_per_bird=Decimal('12000.00'),
        )
        feed_mix = FeedMix.objects.create(
            mix_name=FeedMix.LAYER_FORMULA,
            quantity=Decimal('8.00'),
            stock=Decimal('8.00'),
        )

        response = self.client.post(reverse('poultry:record_create', args=['feed-consumption']), {
            'flock': flock.pk,
            'feed_mix': feed_mix.pk,
            'consumption_date': '2026-06-28',
            'quantity': '10.00',
            'issued_by': 'Manager',
            'remarks': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Feed consumption quantity (10kg) cannot exceed feed mix stock (8kg).')
        self.assertFalse(FeedConsumption.objects.exists())

    def test_feed_consumption_update_allows_existing_quantity_in_available_stock(self):
        house = PoultryHouse.objects.create(
            house_name='Layer House Stock Edit',
            capacity=300,
            bird_type=PoultryHouse.LAYER,
            status=PoultryHouse.ACTIVE,
        )
        flock = Flock.objects.create(
            house=house,
            breed=Flock.ISA_BROWN,
            number_of_birds=100,
            current_birds=100,
            cost_per_bird=Decimal('12000.00'),
        )
        feed_mix = FeedMix.objects.create(
            mix_name=FeedMix.LAYER_FORMULA,
            quantity=Decimal('10.00'),
            stock=Decimal('10.00'),
        )
        consumption = FeedConsumption.objects.create(
            flock=flock,
            feed_mix=feed_mix,
            quantity=Decimal('6.00'),
            issued_by='Manager',
        )

        response = self.client.post(reverse('poultry:record_update', args=['feed-consumption', consumption.pk]), {
            'flock': flock.pk,
            'feed_mix': feed_mix.pk,
            'consumption_date': '2026-06-28',
            'quantity': '8.00',
            'issued_by': 'Manager',
            'remarks': '',
        })

        consumption.refresh_from_db()
        feed_mix.refresh_from_db()
        self.assertRedirects(response, reverse('poultry:record_detail', args=['feed-consumption', consumption.pk]))
        self.assertEqual(consumption.quantity, Decimal('8.00'))
        self.assertEqual(feed_mix.stock, Decimal('2.00'))

    def test_feed_mix_details_table_shows_totals_last_row(self):
        item = InventoryItem.objects.create(
            item_name='Cotton Cake',
            category='Feed',
            unit='kg',
            current_stock=Decimal('50.00'),
        )
        feed_mix = FeedMix.objects.create(mix_name='Grower Formula')
        FeedMixDetail.objects.create(
            feed_mix=feed_mix,
            inventory_item=item,
            quantity=Decimal('12.00'),
            unit_price=Decimal('2500.00'),
        )

        response = self.client.get(reverse('poultry:record_list', args=['feed-mix-details']))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Quantity')
        self.assertContains(response, 'Unit Price')
        self.assertContains(response, 'Total Price')
        self.assertContains(response, 'Totals')
        self.assertContains(response, '12kgs')
        self.assertContains(response, 'UGX 2,500')
        self.assertContains(response, 'UGX 30,000')

    def test_feed_mix_detail_form_filters_purchased_items_by_mix_name(self):
        maize_purchase = Purchase.objects.create(
            item_name='Maize Bran',
            category='Feeds',
            quantity=Decimal('50.00'),
            reorder_level=Decimal('5.00'),
            unit_price=Decimal('1500.00'),
        )
        pen_purchase = Purchase.objects.create(
            item_name='Pen',
            category='Stationery',
            quantity=Decimal('10.00'),
            reorder_level=Decimal('2.00'),
            unit_price=Decimal('500.00'),
        )
        feed_mix = FeedMix.objects.create(mix_name='Layer Formula')

        response = self.client.get(reverse('poultry:record_create', args=['feed-mix-details']))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Feed mix')
        self.assertContains(response, str(feed_mix))
        self.assertContains(response, 'Purchased Item')
        self.assertContains(response, maize_purchase.item_name)
        self.assertContains(response, pen_purchase.item_name)
        self.assertContains(response, 'feed-item-prices')
        self.assertContains(response, 'feed-mix-purchase-options')
        self.assertContains(response, str(feed_mix.pk))
        self.assertContains(response, '1500.00')
        self.assertContains(response, '50kgs')
        self.assertContains(response, str(maize_purchase.pk))
        self.assertNotIn(pen_purchase.pk, FeedMix.objects.get(pk=feed_mix.pk).allowed_item_names)

    def test_feed_mix_detail_saves_from_selected_feed_mix_purchase(self):
        purchase = Purchase.objects.create(
            item_name='Cotton Cake',
            category='Feeds',
            quantity=Decimal('20.00'),
            reorder_level=Decimal('5.00'),
            unit_price=Decimal('2500.00'),
        )
        feed_mix = FeedMix.objects.create(mix_name='Grower Formula')

        response = self.client.post(reverse('poultry:record_create', args=['feed-mix-details']), {
            'feed_mix': feed_mix.pk,
            'purchase': purchase.pk,
            'quantity': '6.00',
        })

        detail = FeedMixDetail.objects.get(feed_mix=feed_mix)
        purchase.inventory_item.refresh_from_db()
        self.assertRedirects(response, reverse('poultry:record_detail', args=['feed-mix-details', detail.pk]))
        self.assertEqual(detail.purchase, purchase)
        self.assertEqual(detail.inventory_item, purchase.inventory_item)
        self.assertEqual(detail.unit_price, Decimal('2500.00'))
        self.assertEqual(detail.total_price, Decimal('15000.0000'))
        self.assertEqual(purchase.inventory_item.current_stock, Decimal('14.00'))
        purchase.refresh_from_db()
        self.assertEqual(purchase.stock_balance, Decimal('14.00'))

        detail.quantity = Decimal('4.00')
        detail.save()
        purchase.refresh_from_db()
        self.assertEqual(purchase.stock_balance, Decimal('16.00'))

        detail.delete()
        purchase.refresh_from_db()
        self.assertEqual(purchase.stock_balance, Decimal('20.00'))

    def test_feed_mix_detail_rejects_purchase_not_in_mix_recipe(self):
        purchase = Purchase.objects.create(
            item_name='Pen',
            category='Stationery',
            quantity=Decimal('10.00'),
            reorder_level=Decimal('2.00'),
            unit_price=Decimal('500.00'),
        )
        feed_mix = FeedMix.objects.create(mix_name='Layer Formula')

        response = self.client.post(reverse('poultry:record_create', args=['feed-mix-details']), {
            'feed_mix': feed_mix.pk,
            'purchase': purchase.pk,
            'quantity': '2.00',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pen is not part of the Layer Formula recipe.')
        self.assertFalse(FeedMixDetail.objects.exists())
