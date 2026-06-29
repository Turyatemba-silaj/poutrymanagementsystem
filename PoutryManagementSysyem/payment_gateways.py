import base64
import json
import os
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from django.utils import timezone


class PaymentGatewayError(Exception):
    pass


class PaymentConfigurationError(PaymentGatewayError):
    pass


def env(name, default=''):
    return os.environ.get(name, default).strip()


def normalize_uganda_msisdn(mobile_number):
    number = ''.join(char for char in mobile_number if char.isdigit())
    if number.startswith('0') and len(number) == 10:
        return f'256{number[1:]}'
    if number.startswith('256') and len(number) == 12:
        return number
    return number


def json_request(url, method='GET', headers=None, payload=None, timeout=25):
    body = None
    request_headers = headers or {}
    if payload is not None:
        body = json.dumps(payload).encode('utf-8')
        request_headers = {'Content-Type': 'application/json', **request_headers}

    request = Request(url, data=body, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            content = response.read().decode('utf-8')
            if not content:
                return response.status, {}
            return response.status, json.loads(content)
    except HTTPError as error:
        detail = error.read().decode('utf-8')
        raise PaymentGatewayError(f'Payment provider returned {error.code}: {detail or error.reason}') from error
    except URLError as error:
        raise PaymentGatewayError(f'Could not reach payment provider: {error.reason}') from error
    except json.JSONDecodeError as error:
        raise PaymentGatewayError('Payment provider returned an invalid response.') from error


class SimulatorGateway:
    code = 'simulator'
    name = 'Simulator Demo'
    phone_hint = '07XXXXXXXX'

    def configured(self):
        return True

    def request_payment(self, mobile_number, amount, external_id):
        transaction_id = f'SIMULATOR-{timezone.now().strftime("%Y%m%d%H%M%S")}-{uuid4().hex[:8].upper()}'
        return {
            'transaction_id': transaction_id,
            'status': 'approval_sent',
            'message': 'Demo payment approved locally. No PIN prompt was sent to the customer phone.',
            'simulated': True,
        }

    def payment_status(self, transaction_id):
        return 'approved'


class MtnMomoGateway:
    code = 'mtn'
    name = 'MTN Mobile Money'
    phone_hint = '077XXXXXXX / 078XXXXXXX'

    def configured(self):
        return all([
            env('MTN_MOMO_BASE_URL'),
            env('MTN_MOMO_SUBSCRIPTION_KEY'),
            env('MTN_MOMO_API_USER'),
            env('MTN_MOMO_API_KEY'),
            env('MTN_MOMO_TARGET_ENVIRONMENT'),
        ])

    def headers(self, extra=None):
        return {
            'Ocp-Apim-Subscription-Key': env('MTN_MOMO_SUBSCRIPTION_KEY'),
            'X-Target-Environment': env('MTN_MOMO_TARGET_ENVIRONMENT'),
            **(extra or {}),
        }

    def token(self):
        credentials = f'{env("MTN_MOMO_API_USER")}:{env("MTN_MOMO_API_KEY")}'
        encoded = base64.b64encode(credentials.encode('utf-8')).decode('ascii')
        status, data = json_request(
            f'{env("MTN_MOMO_BASE_URL").rstrip("/")}/collection/token/',
            method='POST',
            headers=self.headers({'Authorization': f'Basic {encoded}'}),
        )
        if status not in {200, 201} or not data.get('access_token'):
            raise PaymentGatewayError('MTN did not return an access token.')
        return data['access_token']

    def request_payment(self, mobile_number, amount, external_id):
        reference_id = str(uuid4())
        access_token = self.token()
        payer_number = normalize_uganda_msisdn(mobile_number)
        payload = {
            'amount': str(Decimal(amount)),
            'currency': env('MTN_MOMO_CURRENCY', 'UGX'),
            'externalId': external_id,
            'payer': {
                'partyIdType': 'MSISDN',
                'partyId': payer_number,
            },
            'payerMessage': env('MTN_MOMO_PAYER_MESSAGE', 'Poultry egg sale payment'),
            'payeeNote': env('MTN_MOMO_PAYEE_NOTE', 'Poultry Management System'),
        }
        status, _ = json_request(
            f'{env("MTN_MOMO_BASE_URL").rstrip("/")}/collection/v1_0/requesttopay',
            method='POST',
            headers=self.headers({
                'Authorization': f'Bearer {access_token}',
                'X-Reference-Id': reference_id,
            }),
            payload=payload,
        )
        if status not in {200, 201, 202}:
            raise PaymentGatewayError('MTN payment request was not accepted.')
        return {
            'transaction_id': reference_id,
            'status': 'approval_sent',
            'message': f'MTN Mobile Money PIN prompt sent to {mobile_number}. Ask the customer to approve on their phone.',
            'simulated': False,
        }

    def payment_status(self, transaction_id):
        access_token = self.token()
        _, data = json_request(
            f'{env("MTN_MOMO_BASE_URL").rstrip("/")}/collection/v1_0/requesttopay/{transaction_id}',
            headers=self.headers({'Authorization': f'Bearer {access_token}'}),
        )
        return (data.get('status') or 'pending').lower()


class AirtelMoneyGateway:
    code = 'airtel'
    name = 'Airtel Money'
    phone_hint = '070XXXXXXX / 075XXXXXXX'

    def configured(self):
        return all([
            env('AIRTEL_MONEY_REQUEST_URL'),
            env('AIRTEL_MONEY_STATUS_URL'),
            env('AIRTEL_MONEY_CLIENT_ID'),
            env('AIRTEL_MONEY_CLIENT_SECRET'),
        ])

    def headers(self):
        return {
            'X-Client-Id': env('AIRTEL_MONEY_CLIENT_ID'),
            'X-Client-Secret': env('AIRTEL_MONEY_CLIENT_SECRET'),
        }

    def request_payment(self, mobile_number, amount, external_id):
        payer_number = normalize_uganda_msisdn(mobile_number)
        payload = {
            'reference': external_id,
            'msisdn': payer_number,
            'amount': str(Decimal(amount)),
            'currency': env('AIRTEL_MONEY_CURRENCY', 'UGX'),
            'country': env('AIRTEL_MONEY_COUNTRY', 'UG'),
        }
        _, data = json_request(
            env('AIRTEL_MONEY_REQUEST_URL'),
            method='POST',
            headers=self.headers(),
            payload=payload,
        )
        transaction_id = data.get('transaction_id') or data.get('id') or external_id
        return {
            'transaction_id': transaction_id,
            'status': data.get('status', 'approval_sent'),
            'message': f'Airtel Money PIN prompt sent to {mobile_number}. Ask the customer to approve on their phone.',
            'simulated': False,
        }

    def payment_status(self, transaction_id):
        status_url = env('AIRTEL_MONEY_STATUS_URL').format(transaction_id=transaction_id)
        _, data = json_request(status_url, headers=self.headers())
        return (data.get('status') or data.get('transaction_status') or 'pending').lower()


GATEWAYS = {
    'simulator': SimulatorGateway(),
    'mtn': MtnMomoGateway(),
    'airtel': AirtelMoneyGateway(),
}


def provider_options():
    return [
        {
            'code': code,
            'name': gateway.name,
            'phone_hint': gateway.phone_hint,
            'active': gateway.configured(),
            'simulated': code == 'simulator',
        }
        for code, gateway in GATEWAYS.items()
    ]
