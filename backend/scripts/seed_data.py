"""
Seed script — loads customers, claims, embeddings, and regulatory rules.

Run with:
    uv run python db/seeds/seed_data.py
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from sentence_transformers import SentenceTransformer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from underwriting.platform.database.models import (
    Claim,
    ClaimsEmbedding,
    Customer,
    Regulation,
)

DATABASE_URL = "postgresql+asyncpg://qbe:localdev@localhost:5432/aus_underwriting"

# ── Customers ─────────────────────────────────────────────────────────────────
# Pre-generate UUIDs so claims can reference them immediately

CUSTOMERS = [
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "customer_ref": "CUST-NZ-001",
        "entity_type": "INDIVIDUAL",
        "full_name": "James Tane",
        "trading_name": None,
        "abn_nzbn": None,
        "email": "james.tane@email.co.nz",
        "phone": "+64 9 555 0101",
        "address_line1": "14 Remuera Road",
        "city": "Auckland",
        "region": "Auckland",
        "jurisdiction": "NZ",
        "kyc_status": "VERIFIED",
        "kyc_verified_at": datetime(2021, 3, 10, tzinfo=timezone.utc),
        "is_blacklisted": False,
        "blacklist_reason": None,
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000002"),
        "customer_ref": "CUST-NZ-002",
        "entity_type": "COMPANY",
        "full_name": "Pacific Properties Limited",
        "trading_name": "Pacific Properties",
        "abn_nzbn": "9429041235876",
        "email": "admin@pacificproperties.co.nz",
        "phone": "+64 3 555 0202",
        "address_line1": "88 Colombo Street",
        "city": "Christchurch",
        "region": "Canterbury",
        "jurisdiction": "NZ",
        "kyc_status": "VERIFIED",
        "kyc_verified_at": datetime(2020, 8, 15, tzinfo=timezone.utc),
        "is_blacklisted": False,
        "blacklist_reason": None,
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000003"),
        "customer_ref": "CUST-NZ-003",
        "entity_type": "INDIVIDUAL",
        "full_name": "Sarah Whitmore",
        "trading_name": None,
        "abn_nzbn": None,
        "email": "sarah.whitmore@gmail.com",
        "phone": "+64 4 555 0303",
        "address_line1": "52 Tinakori Road",
        "city": "Wellington",
        "region": "Wellington",
        "jurisdiction": "NZ",
        "kyc_status": "VERIFIED",
        "kyc_verified_at": datetime(2019, 11, 20, tzinfo=timezone.utc),
        "is_blacklisted": False,
        "blacklist_reason": None,
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000004"),
        "customer_ref": "CUST-NZ-004",
        "entity_type": "COMPANY",
        "full_name": "Te Aro Holdings Limited",
        "trading_name": "Te Aro Holdings",
        "abn_nzbn": "9429088123456",
        "email": "info@tearoholdings.co.nz",
        "phone": "+64 6 555 0404",
        "address_line1": "23 Marine Parade",
        "city": "Napier",
        "region": "Hawke's Bay",
        "jurisdiction": "NZ",
        "kyc_status": "VERIFIED",
        "kyc_verified_at": datetime(2022, 1, 5, tzinfo=timezone.utc),
        "is_blacklisted": False,
        "blacklist_reason": None,
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000005"),
        "customer_ref": "CUST-NZ-005",
        "entity_type": "INDIVIDUAL",
        "full_name": "Michael Chen",
        "trading_name": None,
        "abn_nzbn": None,
        "email": "michael.chen@xtra.co.nz",
        "phone": "+64 9 555 0505",
        "address_line1": "7 Ponsonby Road",
        "city": "Auckland",
        "region": "Auckland",
        "jurisdiction": "NZ",
        "kyc_status": "VERIFIED",
        "kyc_verified_at": datetime(2020, 6, 30, tzinfo=timezone.utc),
        "is_blacklisted": False,
        "blacklist_reason": None,
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000006"),
        "customer_ref": "CUST-NZ-006",
        "entity_type": "INDIVIDUAL",
        "full_name": "David Harrington",
        "trading_name": None,
        "abn_nzbn": None,
        "email": "d.harrington@hotmail.com",
        "phone": "+64 9 555 0606",
        "address_line1": "3 Hillcrest Avenue",
        "city": "Auckland",
        "region": "Auckland",
        "jurisdiction": "NZ",
        "kyc_status": "VERIFIED",
        "kyc_verified_at": datetime(2018, 5, 14, tzinfo=timezone.utc),
        "is_blacklisted": False,
        "blacklist_reason": None,
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000007"),
        "customer_ref": "CUST-NZ-007",
        "entity_type": "INDIVIDUAL",
        "full_name": "Rachel Sutherland",
        "trading_name": None,
        "abn_nzbn": None,
        "email": "rachel.sutherland@otago.ac.nz",
        "phone": "+64 3 555 0707",
        "address_line1": "19 Signal Hill Road",
        "city": "Dunedin",
        "region": "Otago",
        "jurisdiction": "NZ",
        "kyc_status": "VERIFIED",
        "kyc_verified_at": datetime(2021, 9, 22, tzinfo=timezone.utc),
        "is_blacklisted": False,
        "blacklist_reason": None,
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000008"),
        "customer_ref": "CUST-NZ-008",
        "entity_type": "INDIVIDUAL",
        "full_name": "Bruce Ngata",
        "trading_name": None,
        "abn_nzbn": None,
        "email": "bruce.ngata@paradise.net.nz",
        "phone": "+64 6 555 0808",
        "address_line1": "45 Hastings Street",
        "city": "Napier",
        "region": "Hawke's Bay",
        "jurisdiction": "NZ",
        "kyc_status": "VERIFIED",
        "kyc_verified_at": datetime(2017, 4, 8, tzinfo=timezone.utc),
        "is_blacklisted": False,
        "blacklist_reason": None,
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000009"),
        "customer_ref": "CUST-AU-001",
        "entity_type": "COMPANY",
        "full_name": "Harbour View Management Pty Ltd",
        "trading_name": "Harbour View Management",
        "abn_nzbn": "51 824 753 556",
        "email": "admin@harbourview.com.au",
        "phone": "+61 2 5550 0901",
        "address_line1": "Level 12, 1 Macquarie Place",
        "city": "Sydney",
        "region": "New South Wales",
        "jurisdiction": "AU",
        "kyc_status": "VERIFIED",
        "kyc_verified_at": datetime(2020, 3, 15, tzinfo=timezone.utc),
        "is_blacklisted": False,
        "blacklist_reason": None,
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000010"),
        "customer_ref": "CUST-AU-002",
        "entity_type": "COMPANY",
        "full_name": "Brisbane River Traders Pty Ltd",
        "trading_name": "BR Traders",
        "abn_nzbn": "78 234 891 002",
        "email": "accounts@brtraders.com.au",
        "phone": "+61 7 5550 1002",
        "address_line1": "200 Eagle Street",
        "city": "Brisbane",
        "region": "Queensland",
        "jurisdiction": "AU",
        "kyc_status": "VERIFIED",
        "kyc_verified_at": datetime(2019, 7, 20, tzinfo=timezone.utc),
        "is_blacklisted": False,
        "blacklist_reason": None,
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000011"),
        "customer_ref": "CUST-AU-003",
        "entity_type": "INDIVIDUAL",
        "full_name": "Emma Kowalski",
        "trading_name": None,
        "abn_nzbn": None,
        "email": "emma.kowalski@bigpond.com",
        "phone": "+61 3 5550 1103",
        "address_line1": "27 Brunswick Street",
        "city": "Melbourne",
        "region": "Victoria",
        "jurisdiction": "AU",
        "kyc_status": "VERIFIED",
        "kyc_verified_at": datetime(2021, 12, 1, tzinfo=timezone.utc),
        "is_blacklisted": False,
        "blacklist_reason": None,
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000012"),
        "customer_ref": "CUST-AU-004",
        "entity_type": "INDIVIDUAL",
        "full_name": "Craig Donaldson",
        "trading_name": None,
        "abn_nzbn": None,
        "email": "craig.donaldson@iinet.net.au",
        "phone": "+61 8 5550 1204",
        "address_line1": "9 Swan River Drive",
        "city": "Perth",
        "region": "Western Australia",
        "jurisdiction": "AU",
        "kyc_status": "VERIFIED",
        "kyc_verified_at": datetime(2020, 10, 5, tzinfo=timezone.utc),
        "is_blacklisted": False,
        "blacklist_reason": None,
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000013"),
        "customer_ref": "CUST-AU-005",
        "entity_type": "COMPANY",
        "full_name": "Coastal Retail Group Pty Ltd",
        "trading_name": "Coastal Retail",
        "abn_nzbn": "33 456 123 789",
        "email": "finance@coastalretail.com.au",
        "phone": "+61 7 5550 1305",
        "address_line1": "Shop 45, Pacific Fair Shopping Centre",
        "city": "Gold Coast",
        "region": "Queensland",
        "jurisdiction": "AU",
        "kyc_status": "VERIFIED",
        "kyc_verified_at": datetime(2022, 2, 28, tzinfo=timezone.utc),
        "is_blacklisted": False,
        "blacklist_reason": None,
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000014"),
        "customer_ref": "CUST-AU-006",
        "entity_type": "INDIVIDUAL",
        "full_name": "Karen Mitchell",
        "trading_name": None,
        "abn_nzbn": None,
        "email": "karen.mitchell@darwin.net.au",
        "phone": "+61 8 5550 1406",
        "address_line1": "5 Nightcliff Road",
        "city": "Darwin",
        "region": "Northern Territory",
        "jurisdiction": "AU",
        "kyc_status": "VERIFIED",
        "kyc_verified_at": datetime(2019, 6, 14, tzinfo=timezone.utc),
        "is_blacklisted": False,
        "blacklist_reason": None,
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000015"),
        "customer_ref": "CUST-AU-007",
        "entity_type": "INDIVIDUAL",
        "full_name": "Raymond Xu",
        "trading_name": None,
        "abn_nzbn": None,
        "email": "raymond.xu@cairns.net.au",
        "phone": "+61 7 5550 1507",
        "address_line1": "12 Esplanade",
        "city": "Cairns",
        "region": "Queensland",
        "jurisdiction": "AU",
        "kyc_status": "VERIFIED",
        "kyc_verified_at": datetime(2018, 9, 3, tzinfo=timezone.utc),
        "is_blacklisted": False,
        "blacklist_reason": None,
    },
]

# ── Claims ────────────────────────────────────────────────────────────────────
# Pre-generate UUIDs so embeddings can reference them immediately

CLAIMS = [
    {
        "id": uuid.UUID("10000000-0000-0000-0000-000000000001"),
        "claim_number": "CLM-NZ-2023-001",
        "customer_id": uuid.UUID("00000000-0000-0000-0000-000000000001"),  # James Tane
        "policy_id": None,
        "class_of_business": "property",
        "jurisdiction": "NZ",
        "risk_address_region": "Auckland, New Zealand",
        "claim_date": datetime(2023, 6, 15, tzinfo=timezone.utc),
        "date_reported": datetime(2023, 6, 16, tzinfo=timezone.utc),
        "cause_of_loss": "water_damage",
        "incurred_amount": 45000.00,
        "reserved_amount": 50000.00,
        "currency": "NZD",
        "status": "SETTLED",
        "is_large_loss": False,
        "fraud_flag": False,
        "fraud_investigation_status": None,
        "settled_at": datetime(2023, 8, 20, tzinfo=timezone.utc),
        "claim_summary": (
            "Residential property in Auckland suffered significant water damage due to a burst pipe "
            "in the upstairs bathroom. Damage extended to ceilings, flooring, and internal walls on "
            "the ground floor. Remediation included full drying, mould treatment, and reinstatement "
            "of affected surfaces. Claim settled at NZD 45,000."
        ),
    },
    {
        "id": uuid.UUID("10000000-0000-0000-0000-000000000002"),
        "claim_number": "CLM-NZ-2023-002",
        "customer_id": uuid.UUID("00000000-0000-0000-0000-000000000002"),  # Pacific Properties
        "policy_id": None,
        "class_of_business": "property",
        "jurisdiction": "NZ",
        "risk_address_region": "Christchurch, New Zealand",
        "claim_date": datetime(2023, 2, 20, tzinfo=timezone.utc),
        "date_reported": datetime(2023, 2, 21, tzinfo=timezone.utc),
        "cause_of_loss": "earthquake",
        "incurred_amount": 320000.00,
        "reserved_amount": 350000.00,
        "currency": "NZD",
        "status": "SETTLED",
        "is_large_loss": True,
        "fraud_flag": False,
        "fraud_investigation_status": None,
        "settled_at": datetime(2023, 9, 10, tzinfo=timezone.utc),
        "claim_summary": (
            "Commercial building in Christchurch sustained structural damage following a magnitude "
            "5.8 earthquake. Foundation cracking and internal wall separation observed. Engineering "
            "assessment confirmed the structure required partial demolition and full foundation "
            "reinstatement. Total loss settled at NZD 320,000 including temporary relocation costs."
        ),
    },
    {
        "id": uuid.UUID("10000000-0000-0000-0000-000000000003"),
        "claim_number": "CLM-NZ-2022-001",
        "customer_id": uuid.UUID("00000000-0000-0000-0000-000000000003"),  # Sarah Whitmore
        "policy_id": None,
        "class_of_business": "property",
        "jurisdiction": "NZ",
        "risk_address_region": "Wellington, New Zealand",
        "claim_date": datetime(2022, 8, 5, tzinfo=timezone.utc),
        "date_reported": datetime(2022, 8, 6, tzinfo=timezone.utc),
        "cause_of_loss": "storm_damage",
        "incurred_amount": 28000.00,
        "reserved_amount": 30000.00,
        "currency": "NZD",
        "status": "SETTLED",
        "is_large_loss": False,
        "fraud_flag": False,
        "fraud_investigation_status": None,
        "settled_at": datetime(2022, 9, 15, tzinfo=timezone.utc),
        "claim_summary": (
            "Residential property in Wellington sustained roof damage during a severe storm event "
            "with winds exceeding 120 km/h. Multiple roof tiles displaced, guttering detached, and "
            "water ingress caused damage to ceiling insulation and internal plasterboard. Repairs "
            "completed within four weeks. Claim settled at NZD 28,000."
        ),
    },
    {
        "id": uuid.UUID("10000000-0000-0000-0000-000000000004"),
        "claim_number": "CLM-NZ-2023-003",
        "customer_id": uuid.UUID("00000000-0000-0000-0000-000000000004"),  # Te Aro Holdings
        "policy_id": None,
        "class_of_business": "property",
        "jurisdiction": "NZ",
        "risk_address_region": "Hawke's Bay, New Zealand",
        "claim_date": datetime(2023, 2, 14, tzinfo=timezone.utc),
        "date_reported": datetime(2023, 2, 16, tzinfo=timezone.utc),
        "cause_of_loss": "flood",
        "incurred_amount": 185000.00,
        "reserved_amount": 200000.00,
        "currency": "NZD",
        "status": "SETTLED",
        "is_large_loss": True,
        "fraud_flag": False,
        "fraud_investigation_status": None,
        "settled_at": datetime(2023, 11, 30, tzinfo=timezone.utc),
        "claim_summary": (
            "Cyclone Gabrielle caused severe flooding across Hawke's Bay. Residential property "
            "inundated with up to 1.2 metres of floodwater. Contents total loss, structural "
            "damage to ground floor, and complete replacement of electrical systems required. "
            "Property uninhabitable for six months. Settled at NZD 185,000."
        ),
    },
    {
        "id": uuid.UUID("10000000-0000-0000-0000-000000000005"),
        "claim_number": "CLM-NZ-2023-004",
        "customer_id": uuid.UUID("00000000-0000-0000-0000-000000000005"),  # Michael Chen
        "policy_id": None,
        "class_of_business": "property",
        "jurisdiction": "NZ",
        "risk_address_region": "Auckland, New Zealand",
        "claim_date": datetime(2023, 1, 27, tzinfo=timezone.utc),
        "date_reported": datetime(2023, 1, 28, tzinfo=timezone.utc),
        "cause_of_loss": "flood",
        "incurred_amount": 95000.00,
        "reserved_amount": 100000.00,
        "currency": "NZD",
        "status": "SETTLED",
        "is_large_loss": False,
        "fraud_flag": False,
        "fraud_investigation_status": None,
        "settled_at": datetime(2023, 6, 15, tzinfo=timezone.utc),
        "claim_summary": (
            "Auckland Anniversary Weekend flooding event resulted in severe stormwater overflow "
            "affecting multiple properties in low-lying suburbs. This property sustained ground "
            "floor flooding with damage to flooring, cabinetry, and electrical fittings. "
            "Settled at NZD 95,000 including temporary accommodation."
        ),
    },
    {
        "id": uuid.UUID("10000000-0000-0000-0000-000000000006"),
        "claim_number": "CLM-NZ-2022-002",
        "customer_id": uuid.UUID("00000000-0000-0000-0000-000000000006"),  # David Harrington
        "policy_id": None,
        "class_of_business": "property",
        "jurisdiction": "NZ",
        "risk_address_region": "Auckland, New Zealand",
        "claim_date": datetime(2022, 11, 3, tzinfo=timezone.utc),
        "date_reported": datetime(2022, 11, 4, tzinfo=timezone.utc),
        "cause_of_loss": "fire",
        "incurred_amount": 550000.00,
        "reserved_amount": 600000.00,
        "currency": "NZD",
        "status": "SETTLED",
        "is_large_loss": True,
        "fraud_flag": True,
        "fraud_investigation_status": "UNDER_INVESTIGATION",
        "settled_at": datetime(2023, 5, 20, tzinfo=timezone.utc),
        "claim_summary": (
            "Residential property in Auckland completely destroyed by fire. Origin identified as "
            "kitchen. Investigator noted inconsistencies in the insured's account of events and "
            "found the property had recently been over-insured to twice its market value. "
            "Claim subject to fraud investigation. Settled at reduced sum pending outcome."
        ),
    },
    {
        "id": uuid.UUID("10000000-0000-0000-0000-000000000007"),
        "claim_number": "CLM-NZ-2022-003",
        "customer_id": uuid.UUID("00000000-0000-0000-0000-000000000007"),  # Rachel Sutherland
        "policy_id": None,
        "class_of_business": "property",
        "jurisdiction": "NZ",
        "risk_address_region": "Dunedin, New Zealand",
        "claim_date": datetime(2022, 6, 30, tzinfo=timezone.utc),
        "date_reported": datetime(2022, 7, 2, tzinfo=timezone.utc),
        "cause_of_loss": "subsidence",
        "incurred_amount": 240000.00,
        "reserved_amount": 260000.00,
        "currency": "NZD",
        "status": "SETTLED",
        "is_large_loss": True,
        "fraud_flag": False,
        "fraud_investigation_status": None,
        "settled_at": datetime(2023, 2, 28, tzinfo=timezone.utc),
        "claim_summary": (
            "Residential property in Dunedin hill suburb suffered ground subsidence due to "
            "prolonged rainfall saturating clay soils on a steep slope. Foundation movement "
            "caused significant cracking to external walls, internal plasterboard, and roof "
            "framing distortion. Geotechnical report confirmed ongoing slope instability. "
            "Settled at NZD 240,000. Property flagged as high-risk for future cover."
        ),
    },
    {
        "id": uuid.UUID("10000000-0000-0000-0000-000000000008"),
        "claim_number": "CLM-NZ-2021-001",
        "customer_id": uuid.UUID("00000000-0000-0000-0000-000000000008"),  # Bruce Ngata
        "policy_id": None,
        "class_of_business": "property",
        "jurisdiction": "NZ",
        "risk_address_region": "Napier, New Zealand",
        "claim_date": datetime(2021, 5, 20, tzinfo=timezone.utc),
        "date_reported": datetime(2021, 5, 25, tzinfo=timezone.utc),
        "cause_of_loss": "water_damage",
        "incurred_amount": 32000.00,
        "reserved_amount": 35000.00,
        "currency": "NZD",
        "status": "SETTLED",
        "is_large_loss": False,
        "fraud_flag": False,
        "fraud_investigation_status": None,
        "settled_at": datetime(2021, 9, 10, tzinfo=timezone.utc),
        "claim_summary": (
            "Older residential property in Napier experienced gradual water damage from a "
            "slow leak in a corroded water supply pipe within the wall cavity. Damage was "
            "discovered during renovation work. Mould remediation required in addition to "
            "pipe replacement and wall reinstatement. Settled at NZD 32,000."
        ),
    },
    {
        "id": uuid.UUID("10000000-0000-0000-0000-000000000009"),
        "claim_number": "CLM-AU-2023-001",
        "customer_id": uuid.UUID("00000000-0000-0000-0000-000000000009"),  # Harbour View Mgmt
        "policy_id": None,
        "class_of_business": "property",
        "jurisdiction": "AU",
        "risk_address_region": "Sydney, New South Wales, Australia",
        "claim_date": datetime(2023, 3, 10, tzinfo=timezone.utc),
        "date_reported": datetime(2023, 3, 11, tzinfo=timezone.utc),
        "cause_of_loss": "water_damage",
        "incurred_amount": 62000.00,
        "reserved_amount": 70000.00,
        "currency": "AUD",
        "status": "SETTLED",
        "is_large_loss": False,
        "fraud_flag": False,
        "fraud_investigation_status": None,
        "settled_at": datetime(2023, 6, 20, tzinfo=timezone.utc),
        "claim_summary": (
            "Commercial office property in Sydney CBD suffered water ingress from a failed roof "
            "membrane during heavy rainfall. Damage to ceiling tiles, flooring, and IT equipment. "
            "Business interruption claimed for five days. Total settled at AUD 62,000 including "
            "contents and BI component."
        ),
    },
    {
        "id": uuid.UUID("10000000-0000-0000-0000-000000000010"),
        "claim_number": "CLM-AU-2022-001",
        "customer_id": uuid.UUID("00000000-0000-0000-0000-000000000010"),  # Brisbane River Traders
        "policy_id": None,
        "class_of_business": "property",
        "jurisdiction": "AU",
        "risk_address_region": "Brisbane, Queensland, Australia",
        "claim_date": datetime(2022, 3, 1, tzinfo=timezone.utc),
        "date_reported": datetime(2022, 3, 3, tzinfo=timezone.utc),
        "cause_of_loss": "flood",
        "incurred_amount": 420000.00,
        "reserved_amount": 450000.00,
        "currency": "AUD",
        "status": "SETTLED",
        "is_large_loss": True,
        "fraud_flag": False,
        "fraud_investigation_status": None,
        "settled_at": datetime(2022, 12, 15, tzinfo=timezone.utc),
        "claim_summary": (
            "2022 Brisbane floods inundated this riverside commercial property with over two metres "
            "of floodwater. Complete loss of ground floor fit-out, plant and equipment, and "
            "significant structural damage. Remediation took eight months. AUD 420,000 settlement "
            "included structural reinstatement and business interruption for the full remediation period."
        ),
    },
    {
        "id": uuid.UUID("10000000-0000-0000-0000-000000000011"),
        "claim_number": "CLM-AU-2023-002",
        "customer_id": uuid.UUID("00000000-0000-0000-0000-000000000011"),  # Emma Kowalski
        "policy_id": None,
        "class_of_business": "property",
        "jurisdiction": "AU",
        "risk_address_region": "Melbourne, Victoria, Australia",
        "claim_date": datetime(2023, 7, 22, tzinfo=timezone.utc),
        "date_reported": datetime(2023, 7, 23, tzinfo=timezone.utc),
        "cause_of_loss": "storm_damage",
        "incurred_amount": 38000.00,
        "reserved_amount": 40000.00,
        "currency": "AUD",
        "status": "SETTLED",
        "is_large_loss": False,
        "fraud_flag": False,
        "fraud_investigation_status": None,
        "settled_at": datetime(2023, 9, 30, tzinfo=timezone.utc),
        "claim_summary": (
            "Hailstorm event across Melbourne northern suburbs caused extensive roof and facade "
            "damage to this residential property. Solar panel array damaged beyond repair, "
            "guttering replaced, and external paintwork required. Settled at AUD 38,000."
        ),
    },
    {
        "id": uuid.UUID("10000000-0000-0000-0000-000000000012"),
        "claim_number": "CLM-AU-2022-002",
        "customer_id": uuid.UUID("00000000-0000-0000-0000-000000000012"),  # Craig Donaldson
        "policy_id": None,
        "class_of_business": "property",
        "jurisdiction": "AU",
        "risk_address_region": "Perth, Western Australia, Australia",
        "claim_date": datetime(2022, 12, 15, tzinfo=timezone.utc),
        "date_reported": datetime(2022, 12, 16, tzinfo=timezone.utc),
        "cause_of_loss": "fire",
        "incurred_amount": 890000.00,
        "reserved_amount": 950000.00,
        "currency": "AUD",
        "status": "SETTLED",
        "is_large_loss": True,
        "fraud_flag": False,
        "fraud_investigation_status": None,
        "settled_at": datetime(2023, 10, 5, tzinfo=timezone.utc),
        "claim_summary": (
            "Bushfire in Perth Hills destroyed this rural residential property. Total loss of "
            "dwelling, outbuildings, and contents. Fencing and landscaping also destroyed. "
            "Property located in a designated bushfire-prone area. Rebuild estimated at AUD 890,000 "
            "including site clearing, new dwelling construction, and contents replacement."
        ),
    },
    {
        "id": uuid.UUID("10000000-0000-0000-0000-000000000013"),
        "claim_number": "CLM-AU-2023-003",
        "customer_id": uuid.UUID("00000000-0000-0000-0000-000000000013"),  # Coastal Retail Group
        "policy_id": None,
        "class_of_business": "property",
        "jurisdiction": "AU",
        "risk_address_region": "Gold Coast, Queensland, Australia",
        "claim_date": datetime(2023, 5, 8, tzinfo=timezone.utc),
        "date_reported": datetime(2023, 5, 9, tzinfo=timezone.utc),
        "cause_of_loss": "theft",
        "incurred_amount": 22000.00,
        "reserved_amount": 25000.00,
        "currency": "AUD",
        "status": "SETTLED",
        "is_large_loss": False,
        "fraud_flag": False,
        "fraud_investigation_status": None,
        "settled_at": datetime(2023, 7, 14, tzinfo=timezone.utc),
        "claim_summary": (
            "Break-in at commercial retail premises on Gold Coast. Offenders forced entry via "
            "rear roller door and removed cash from safe, electronic point-of-sale equipment, "
            "and stock. CCTV footage confirmed. Settled at AUD 22,000 including security upgrade."
        ),
    },
    {
        "id": uuid.UUID("10000000-0000-0000-0000-000000000014"),
        "claim_number": "CLM-AU-2023-004",
        "customer_id": uuid.UUID("00000000-0000-0000-0000-000000000014"),  # Karen Mitchell
        "policy_id": None,
        "class_of_business": "property",
        "jurisdiction": "AU",
        "risk_address_region": "Darwin, Northern Territory, Australia",
        "claim_date": datetime(2023, 1, 30, tzinfo=timezone.utc),
        "date_reported": datetime(2023, 2, 1, tzinfo=timezone.utc),
        "cause_of_loss": "storm_damage",
        "incurred_amount": 75000.00,
        "reserved_amount": 80000.00,
        "currency": "AUD",
        "status": "SETTLED",
        "is_large_loss": False,
        "fraud_flag": False,
        "fraud_investigation_status": None,
        "settled_at": datetime(2023, 5, 18, tzinfo=timezone.utc),
        "claim_summary": (
            "Cyclone season storm caused wind and rain damage to this residential property in "
            "Darwin. Roof partially lifted, water ingress throughout, and external structures "
            "including carport and fencing destroyed. Settled at AUD 75,000."
        ),
    },
    {
        "id": uuid.UUID("10000000-0000-0000-0000-000000000015"),
        "claim_number": "CLM-AU-2022-003",
        "customer_id": uuid.UUID("00000000-0000-0000-0000-000000000015"),  # Raymond Xu
        "policy_id": None,
        "class_of_business": "property",
        "jurisdiction": "AU",
        "risk_address_region": "Cairns, Queensland, Australia",
        "claim_date": datetime(2022, 2, 8, tzinfo=timezone.utc),
        "date_reported": datetime(2022, 2, 10, tzinfo=timezone.utc),
        "cause_of_loss": "flood",
        "incurred_amount": 155000.00,
        "reserved_amount": 170000.00,
        "currency": "AUD",
        "status": "SETTLED",
        "is_large_loss": True,
        "fraud_flag": False,
        "fraud_investigation_status": None,
        "settled_at": datetime(2022, 10, 22, tzinfo=timezone.utc),
        "claim_summary": (
            "Monsoonal flooding in Cairns inundated this residential property located in a "
            "known flood-affected area. Property had flooded twice previously in the last decade. "
            "Ground floor completely gutted and reinstated. Flood resilience upgrades including "
            "raised electrical fittings completed as part of reinstatement. Settled at AUD 155,000."
        ),
    },
]

# ── Regulatory rules ───────────────────────────────────────────────────────────

REGULATIONS = [
    {
        "regulator": "RBNZ",
        "jurisdiction": "NZ",
        "class_of_business": "property",
        "rule_code": "RBNZ-PROP-001",
        "rule_description": "Minimum sum insured must reflect full replacement cost of the dwelling.",
        "rule_data": {
            "requirement": "sum_insured_must_equal_replacement_cost",
            "minimum_coverage_ratio": 1.0,
            "applies_to": ["residential", "commercial"],
            "enforcement": "mandatory",
            "reference": "Insurance (Prudential Supervision) Act 2010, Section 84",
        },
        "effective_date": datetime(2020, 1, 1, tzinfo=timezone.utc),
        "expiry_date": None,
        "version": "1.0",
    },
    {
        "regulator": "RBNZ",
        "jurisdiction": "NZ",
        "class_of_business": "property",
        "rule_code": "RBNZ-PROP-002",
        "rule_description": "Insurer must disclose natural hazard exclusions clearly in policy wording. NOTE: This is a policy ISSUANCE process requirement fulfilled by the policy administration system at contract creation — it is NOT an underwriting validation check and must not block or refer an otherwise sound submission.",
        "rule_data": {
            "requirement": "natural_hazard_disclosure",
            "category": "policy_issuance_process",
            "covered_hazards": ["earthquake", "flood", "landslip", "volcanic"],
            "disclosure_timing": "pre_contract",
            "enforcement": "mandatory_at_issuance",
            "reference": "Fair Insurance Code 2020, Clause 3.2",
        },
        "effective_date": datetime(2020, 6, 1, tzinfo=timezone.utc),
        "expiry_date": None,
        "version": "1.0",
    },
    {
        "regulator": "RBNZ",
        "jurisdiction": "NZ",
        "class_of_business": "property",
        "rule_code": "RBNZ-PROP-003",
        "rule_description": "EQC levy applies to residential property policies only (dwellings and residential contents). Commercial, industrial, and other non-residential property classes are EXEMPT from EQC levy under the Earthquake Commission Act 1993. Do NOT require EQC levy for commercial property submissions.",
        "rule_data": {
            "requirement": "eqc_levy_collection",
            "applies_to": "residential_only",
            "exempt_classes": ["commercial", "industrial", "mixed_use", "retail", "office"],
            "levy_rate_per_100": 0.20,
            "maximum_levy_per_property": 480.00,
            "currency": "NZD",
            "enforcement": "mandatory_residential_only",
            "reference": "Earthquake Commission Act 1993",
        },
        "effective_date": datetime(2022, 10, 1, tzinfo=timezone.utc),
        "expiry_date": None,
        "version": "2.0",
    },
    {
        "regulator": "RBNZ",
        "jurisdiction": "NZ",
        "class_of_business": "property",
        "rule_code": "RBNZ-PROP-004",
        "rule_description": "High-value RESIDENTIAL property policies above NZD 5M require senior underwriter sign-off. Commercial property authority limits are governed separately by delegated authority schedules — this rule does NOT apply to commercial submissions.",
        "rule_data": {
            "requirement": "high_value_residential_approval",
            "applies_to": "residential_only",
            "threshold_nzd": 5000000,
            "approval_level": "senior_underwriter",
            "documentation_required": ["valuation_report", "risk_survey"],
            "enforcement": "mandatory_residential_only",
        },
        "effective_date": datetime(2021, 1, 1, tzinfo=timezone.utc),
        "expiry_date": None,
        "version": "1.0",
    },
    {
        "regulator": "APRA",
        "jurisdiction": "AU",
        "class_of_business": "property",
        "rule_code": "APRA-PROP-001",
        "rule_description": "General insurers must maintain minimum capital requirements under GPS 110.",
        "rule_data": {
            "requirement": "minimum_capital_adequacy",
            "standard": "GPS_110",
            "minimum_capital_ratio": 1.0,
            "applies_to": "all_general_insurers",
            "enforcement": "mandatory",
            "reference": "Prudential Standard GPS 110",
        },
        "effective_date": datetime(2023, 1, 1, tzinfo=timezone.utc),
        "expiry_date": None,
        "version": "3.0",
    },
    {
        "regulator": "APRA",
        "jurisdiction": "AU",
        "class_of_business": "property",
        "rule_code": "APRA-PROP-002",
        "rule_description": "Flood must be offered as standard cover; exclusion requires explicit customer opt-out.",
        "rule_data": {
            "requirement": "flood_cover_default_inclusion",
            "default": "included",
            "opt_out_allowed": True,
            "opt_out_must_be": "written_and_explicit",
            "enforcement": "mandatory",
            "reference": "Insurance Contracts Act 1984, Section 54",
        },
        "effective_date": datetime(2012, 6, 1, tzinfo=timezone.utc),
        "expiry_date": None,
        "version": "1.0",
    },
    {
        "regulator": "APRA",
        "jurisdiction": "AU",
        "class_of_business": "property",
        "rule_code": "APRA-PROP-003",
        "rule_description": "Target Market Determination (TMD) must be documented for each product.",
        "rule_data": {
            "requirement": "target_market_determination",
            "review_frequency": "annual",
            "triggers_for_review": ["significant_dealing", "complaints_threshold"],
            "enforcement": "mandatory",
            "reference": "Corporations Act 2001, Section 994B",
        },
        "effective_date": datetime(2021, 10, 5, tzinfo=timezone.utc),
        "expiry_date": None,
        "version": "1.0",
    },
    {
        "regulator": "APRA",
        "jurisdiction": "AU",
        "class_of_business": "property",
        "rule_code": "APRA-PROP-004",
        "rule_description": "Policies above AUD 10M sum insured require reinsurance treaty coverage.",
        "rule_data": {
            "requirement": "reinsurance_for_high_value",
            "threshold_aud": 10000000,
            "reinsurance_type": "treaty_or_facultative",
            "documentation_required": ["reinsurance_slip", "risk_survey"],
            "enforcement": "mandatory",
            "reference": "GPS 116 Reinsurance Management",
        },
        "effective_date": datetime(2023, 1, 1, tzinfo=timezone.utc),
        "expiry_date": None,
        "version": "2.0",
    },
]


# ── Seed runner ────────────────────────────────────────────────────────────────

async def seed(session: AsyncSession) -> None:
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    print("Clearing existing data...")
    await session.execute(text("DELETE FROM claims_embeddings"))
    await session.execute(text("DELETE FROM claims"))
    await session.execute(text("DELETE FROM regulations"))
    await session.commit()

    print(f"\nSeeding {len(CUSTOMERS)} customers (upsert — safe to re-run)...")
    for i, c in enumerate(CUSTOMERS, 1):
        stmt = pg_insert(Customer).values(**c).on_conflict_do_nothing(index_elements=["id"])
        await session.execute(stmt)
        print(f"  [{i:02d}/{len(CUSTOMERS)}] {c['customer_ref']} — {c['full_name']}")
    await session.flush()

    print(f"\nSeeding {len(CLAIMS)} claims...")
    for i, c in enumerate(CLAIMS, 1):
        session.add(Claim(**c))
        print(f"  [{i:02d}/{len(CLAIMS)}] {c['claim_number']} — {c['cause_of_loss']}")
    await session.flush()
    await session.commit()
    print(f"  Claims committed.")

    print("\nLoading sentence-transformers model (all-MiniLM-L6-v2)...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    print("Model loaded.")

    print(f"\nGenerating embeddings for {len(CLAIMS)} claims...")
    for i, c in enumerate(CLAIMS, 1):
        customer = next(x for x in CUSTOMERS if x["id"] == c["customer_id"])
        embedding = model.encode(c["claim_summary"]).tolist()
        session.add(ClaimsEmbedding(
            claim_id=c["id"],
            customer_id=c["customer_id"],
            customer_ref=customer["customer_ref"],
            risk_address_region=c["risk_address_region"],
            class_of_business=c["class_of_business"],
            jurisdiction=c["jurisdiction"],
            claim_date=c["claim_date"],
            cause_of_loss=c["cause_of_loss"],
            incurred_amount=c["incurred_amount"],
            currency=c["currency"],
            is_large_loss=c["is_large_loss"],
            fraud_flag=c["fraud_flag"],
            claim_summary=c["claim_summary"],
            embedding=embedding,
        ))
        print(f"  [{i:02d}/{len(CLAIMS)}] Embedded {c['claim_number']}")
    await session.commit()
    print(f"  Embeddings committed.")

    print(f"\nSeeding {len(REGULATIONS)} regulatory rules...")
    for i, reg in enumerate(REGULATIONS, 1):
        session.add(Regulation(**reg))
        print(f"  [{i:02d}/{len(REGULATIONS)}] {reg['rule_code']} — {reg['regulator']}")
    await session.commit()
    print(f"  Regulations committed.")
    print("\nSeed complete.")
    print(f"  Customers : {len(CUSTOMERS)}")
    print(f"  Claims    : {len(CLAIMS)}")
    print(f"  Embeddings: {len(CLAIMS)}")
    print(f"  Regulations: {len(REGULATIONS)}")


async def main() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        await seed(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
