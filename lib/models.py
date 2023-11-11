import abc
import argparse
import asyncio
import enum
import functools
import inspect
import json
import os
import pprint
import sys
import typing


class FireflyObject:

    ENDPOINT = None
    MONARCH_API_SYMBOL = None
    MONARCH_ID_INDEX = {}
    MONARCH_UNPACK_KEY = None

    @classmethod
    async def all(cls, client):
        # TODO: probably respect pagination
        response = await client.get(cls.ENDPOINT, params={'limit': 100})
        data = await response.json()

        for raw in data['data']:
            instance = cls.from_raw(raw=raw)
            cls.MONARCH_ID_INDEX[instance.monarch_id] = instance

            yield instance

    @classmethod
    async def from_id(cls, id, client):
        response = await client.get(f'{cls.ENDPOINT}/{id}')
        data = await response.json()
        return cls.from_raw(raw=data['data'])

    @classmethod
    async def from_monarch_id(cls, monarch_id, client):
        if monarch_id in cls.MONARCH_ID_INDEX:
            return cls

        async for instance in cls.all(client):
            if instance.monarch_id == monarch_id:
                return instance

        return None

    @classmethod
    async def from_monarch_instance(cls, monarch_instance, client):
        monarch_id = monarch_instance['id']

        if monarch_id in cls.MONARCH_ID_INDEX:
            return cls.MONARCH_ID_INDEX[monarch_id]

        instance = await cls.from_monarch_id(monarch_id, client)

        if instance:
            return instance

        return await cls._from_monarch_instance_impl(monarch_instance, client)

    @classmethod
    def unpack_monarch_response(cls, response):
        return response.get(cls.MONARCH_UNPACK_KEY)

    @classmethod
    async def _from_monarch_instance_impl(cls, monarch_instance, client):
        return cls(
            name=monarch_instance['name'],
            notes=json.dumps({
                'monarchmoney': {
                    'id': monarch_instance['id'],
                },
            }),
        )

    @classmethod
    def from_raw(cls, *, raw):
        return cls(
            name=raw['attributes']['name'],
            notes=raw['attributes']['notes'],
            raw=raw,
        )

    def __init__(self, *, name: str, notes: str, raw = None):
        self._name = name
        self._raw = raw

        if notes:
            self._notes = json.loads(notes)
        else:
            self._notes = {}

    @property
    def id(self):
        return self._raw['id']

    @property
    def monarch_id(self):
        return str(self._notes.get('monarchmoney', {}).get('id'))

    async def create(self, client):
        if self._raw:
            return self

        request = self.serialize()
        response = await client.post(self.ENDPOINT, json=request)
        data = await response.json()
        self._raw = data['data']

        return self

    async def delete(self, client):
        if not self._raw:
            raise RuntimeError('Instance not loaded!')

        response = await client.delete(
            f'{self.ENDPOINT}/{self.id}',
            json=self.serialize(),
        )

        self._raw = None

        return self

    async def update(self, client):
        if not self._raw:
            raise RuntimeError('Instance not loaded!')

        response = await client.update(
            f'{self.ENDPOINT}/{self.id}',
            json=self.serialize(),
        )

        return self

    def serialize(self):
        raise NotImplementedError()


class AssetTypeRole(enum.Enum):

    DEFAULT = 'defaultAsset'
    SHARED = 'sharedAsset'
    SAVING = 'savingAsset'
    CREDIT_CARD = 'ccAsset'
    CASH_WALLET = 'cashWalletAsset'

    @classmethod
    def from_monarch_instance(cls, monarch_instance):
        match monarch_instance:
            case 'cashWalletAsset':
                return cls.CASH_WALLET
            case 'ccAsset':
                return cls.CREDIT_CARD
            case 'credit_card':
                return cls.CREDIT_CARD
            case 'health_savings_account':
                return cls.SAVING
            case 'savingAsset':
                return cls.SAVING
            case 'savings':
                return cls.SAVING
            case 'sharedAsset':
                return cls.SHARED
            case _:
                return cls.DEFAULT


class LiabilityType(enum.Enum):

    DEBT = 'debt'
    LOAN = 'loan'
    MORTGAGE = 'mortgage'

    @classmethod
    def from_monarch_instance(cls, monarch_instance):
        match monarch_instance:
            case 'loan':
                return cls.LOAN
            case 'mortgage':
                return cls.MORTGAGE
            case _:
                return cls.DEBT


class FireflyAccount(FireflyObject):

    ENDPOINT = '/api/v1/accounts'
    MONARCH_API_SYMBOL = 'get_accounts'
    MONARCH_UNPACK_KEY = 'accounts'

    class AccountType(enum.Enum):

        ASSET = 'asset'
        CASH = 'cash'
        EXPENSE = 'expense'
        IMPORT = 'import'
        REVENUE = 'revenue'
        LIABILITY = 'liability'
        LIABILITIES = 'liabilities'
        INITIAL_BALANCE = 'initial-balance'
        RECONCILIATION = 'reconciliation'

        @classmethod
        def from_monarch_instance(cls, monarch_instance):
            match monarch_instance:
                case 'loan':
                    return cls.LIABILITY
                case _:
                    return cls.ASSET

        def subtype_field(self):
            match self:
                case self.ASSET:
                    return 'account_role'
                case self.LIABILITIES:
                    return 'liability_type'
                case self.LIABILITY:
                    return 'liability_type'
                case _:
                    return None

        def subtype(self, monarch_instance):
            match self:
                case self.ASSET:
                    cls = AssetTypeRole
                case self.LIABILITY:
                    cls = LiabilityType
                case _:
                    return None

            return cls.from_monarch_instance(monarch_instance)

    @classmethod
    async def _from_monarch_instance_impl(cls, monarch_instance, client):
        account_type = cls.AccountType.from_monarch_instance(
            monarch_instance['type']['name'],
        )

        return cls(
            name=monarch_instance['displayName'],
            notes=json.dumps({
                'monarchmoney': {
                    'id': monarch_instance['id'],
                },
            }),
            type=account_type,
            subtype=account_type.subtype(monarch_instance['subtype']['name']),
        )

    @classmethod
    def from_raw(cls, *, raw):
        return cls(
            name=raw['attributes']['name'],
            notes=raw['attributes']['notes'],
            type=cls.AccountType(raw['attributes']['type']),
            raw=raw,
        )

    def __init__(
        self,
        *,
        name: str,
        notes: str,
        type: AccountType,
        subtype = None,
        raw = None,
    ):
        super().__init__(name=name, notes=notes, raw=raw)

        self._type = type
        self._subtype = subtype or self._type.subtype(
            raw['attributes'].get(self._type.subtype_field())
        )

    def serialize(self):
        return {
            'name': self._name,
            'notes': json.dumps(self._notes),
            'type': self._type.value,
            'credit_card_type': 'monthlyFull',  # TODO?
            'monthly_payment_date': '2023-01-01T00:00:00',
            'liability_direction': 'debit', # TODO
            **{
                self._type.subtype_field(): self._subtype.value,
            },
        }


class FireflyCategory(FireflyObject):

    ENDPOINT = '/api/v1/categories'
    MONARCH_API_SMYBOL = 'get_transaction_categories'
    MONARCH_UNPACK_KEY = 'categories'

    def serialize(self):
        return {
            'name': self._name,
            'notes': self._notes,
        }


class FireflyTag(FireflyObject):

    ENDPOINT = '/api/v1/tags'
    MONARCH_API_SYMBOL = 'get_tags'
    MONARCH_UNPACK_KEY = 'tags'


class FireflyTransaction(FireflyObject):

    ENDPOINT = '/api/v1/transactions'
    MONARCH_API_SYMBOL = 'get_transactions'

    class TransactionType(enum.Enum):

        DEPOSIT = 'deposit'
        OPENING_BALANCE = 'opening balance'
        RECONCILIATION = 'reconciliation'
        TRANSFER = 'transfer'
        WITHDRAWAL = 'withdrawal'

        @classmethod
        def from_amount(cls, amount):
            if amount < 0:
                return cls.WITHDRAWAL
            if amount > 0:
                return cls.DEPOSIT

    @staticmethod
    def unpack_monarch_response(response):
        return response['allTransactions']['results']

    @classmethod
    async def _from_monarch_instance_impl(cls, monarch_instance, client):
        category = await FireflyCategory.from_monarch_id(
            monarch_instance['category']['id'],
            client,
        )

        tags = [tag['name'] for tag in monarch_instance['tags']]

        type = cls.TransactionType.from_amount(monarch_instance['amount'])

        return cls(
            amount=monarch_instance['amount'],
            # TODO use FireflyAccount instead
            account=monarch_instance['account']['displayName'],
            category=category,
            date=monarch_instance['date'],
            description=monarch_instance['plaidName'],
            # TODO, make a FireflyExpenseAccount
            destination_name=monarch_instance['merchant']['name'],
            tags=tags,
            type=type,
            notes=json.dumps({
                'monarchmoney': {
                    'id': monarch_instance['id'],
                },
            }),
        )

    @classmethod
    def from_raw(cls, *, raw):
        raw = raw['attributes']['transactions'][0]

        return cls(
            account=raw['source_name'],
            amount=float(raw['amount']),
            category=None,
            date=raw['date'],
            description=raw['description'],
            destination_name=raw['destination_name'],
            notes=raw['notes'],
            raw=raw,
            tags=[],
            type=cls.TransactionType(raw['type']),
        )

    def __init__(
        self,
        account: str,
        amount: float,
        category: FireflyCategory,
        date: str,
        description: str,
        destination_name: str,
        tags: typing.List[str],
        type,
        notes: str,
        raw = None,
    ):
        super().__init__(name=None, notes=notes, raw=raw)

        self._account = account
        self._amount = amount
        self._category = category
        self._date = date
        self._description = description
        self._destination_name = destination_name
        self._tags = tags
        self._type = type

    def serialize(self):
        return {
            'apply_rules': True,
            'fire_webhooks': True,
            'group_title': '',
            'transactions': [{
                'amount': abs(self._amount),
                'category_id': self._category.id,
                'date': self._date,
                'description': self._description,
                'destination_name': self._destination_name,
                'external_id': self.monarch_id,
                'notes': json.dumps(self._notes),
                'source_name': self._account,
                'type': self._type.value,
            }],
        }


ALL = FireflyObject.__subclasses__()
