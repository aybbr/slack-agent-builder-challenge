from pathlib import Path

import duckdb

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = str(DATA_DIR / "demo.duckdb")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(DB_PATH) as con:
        con.execute("""
            CREATE OR REPLACE TABLE raw_salesforce_opportunities (
                opportunity_id INTEGER,
                account_id INTEGER,
                amount DECIMAL(12,2),
                stage VARCHAR,
                lead_score INTEGER,
                close_date DATE,
                created_at DATE
            )
        """)

        con.execute("""
            INSERT INTO raw_salesforce_opportunities VALUES
                (1,  101, 50000.00,  'closed_won',    85, '2026-03-15', '2025-12-01'),
                (2,  102, 120000.00, 'negotiation',    72, '2026-06-30', '2026-01-10'),
                (3,  103, 75000.00,  'proposal',       45, '2026-05-20', '2026-02-14'),
                (4,  101, 90000.00,  'qualification',  68, '2026-08-01', '2026-03-05'),
                (5,  104, 30000.00,  'closed_lost',    20, '2026-04-10', '2025-11-20'),
                (6,  105, 200000.00, 'proposal',        95, '2026-07-15', '2026-02-28'),
                (7,  106, 45000.00,  'qualification',   8, '2026-09-01', '2026-04-10'),
                (8,  107, 60000.00,  'negotiation',     55, '2026-06-01', '2026-03-01'),
                (9,  108, 150000.00, 'closed_won',      90, '2026-02-28', '2025-10-15'),
                (10, 102, 85000.00,  'prospecting',     30, '2026-10-01', '2026-05-01'),
                (11, 109, 40000.00,  'qualification',   62, '2026-08-15', '2026-04-20'),
                (12, 103, 110000.00, 'negotiation',     78, '2026-07-01', '2026-03-15'),
                (13, 110, 35000.00,  'prospecting',     15, '2026-11-01', '2026-06-01'),
                (14, 105, 175000.00, 'closed_won',      88, '2026-05-01', '2025-12-20'),
                (15, 111, 220000.00, 'proposal',        92, '2026-07-20', '2026-03-01'),
                (16, 112, 80000.00,  'qualification',   40, '2026-08-30', '2026-04-01'),
                (17, 113, 95000.00,  'negotiation',     65, '2026-06-15', '2026-02-01'),
                (18, 101, 130000.00, 'proposal',        80, '2026-09-15', '2026-05-10'),
                (19, 114, 55000.00,  'prospecting',     25, '2026-10-15', '2026-06-01'),
                (20, 115, 160000.00, 'closed_won',      70, '2026-04-30', '2025-11-15')
        """)

        con.execute("""
            CREATE OR REPLACE TABLE raw_salesforce_accounts (
                account_id INTEGER,
                account_name VARCHAR,
                industry VARCHAR,
                region VARCHAR,
                annual_revenue DECIMAL(14,2),
                employee_count INTEGER,
                is_partner BOOLEAN
            )
        """)

        con.execute("""
            INSERT INTO raw_salesforce_accounts VALUES
                (101, 'Acme Corp',         'Manufacturing', 'North America', 2500000.00,  1200, true),
                (102, 'Globex Industries', 'Technology',    'Europe',        8500000.00,  3500, false),
                (103, 'Initech Solutions', 'Finance',       'Asia Pacific',  1200000.00,   600, false),
                (104, 'Umbrella Holdings', 'Healthcare',    'North America', 5000000.00,  2200, true),
                (105, 'Stark Enterprises', 'Technology',    'Europe',        15000000.00, 5000, false),
                (106, 'Wayne Enterprises', 'Defense',       'North America', 30000000.00, 8000, true),
                (107, 'Oscorp Industries', 'Chemicals',     'Asia Pacific',  1800000.00,   900, false),
                (108, 'LexCorp',           'Energy',        'Europe',        9500000.00,  4000, false),
                (109, 'Vandelay Industries','Manufacturing','North America',  800000.00,   400, false),
                (110, 'Wonka Industries',  'Food & Beverage','Europe',       3500000.00,  1500, true),
                (111, 'Dunder Mifflin',    'Office Supply', 'North America',  450000.00,   200, false),
                (112, 'Hooli',             'Technology',    'North America', 22000000.00, 7000, false),
                (113, 'Pied Piper',        'Technology',    'North America',  300000.00,    50, false),
                (114, 'Massive Dynamic',   'Defense',       'North America', 12000000.00, 4500, true),
                (115, 'Cyberdyne Systems', 'Technology',    'Europe',        7800000.00,  3000, false)
        """)

        con.execute("""
            CREATE OR REPLACE TABLE raw_product_events (
                event_id INTEGER,
                account_id INTEGER,
                feature_id VARCHAR,
                event_type VARCHAR,
                user_count INTEGER,
                event_date DATE
            )
        """)

        con.execute("""
            INSERT INTO raw_product_events VALUES
                (1,  101, 'dashboard',   'view',   45, '2026-06-01'),
                (2,  101, 'reports',     'export', 12, '2026-06-02'),
                (3,  102, 'dashboard',   'view',   89, '2026-06-01'),
                (4,  102, 'pipeline',    'create', 23, '2026-06-03'),
                (5,  103, 'reports',     'view',   15, '2026-06-01'),
                (6,  104, 'dashboard',   'view',   67, '2026-06-02'),
                (7,  105, 'pipeline',    'edit',   42, '2026-06-01'),
                (8,  105, 'dashboard',   'export', 34, '2026-06-03'),
                (9,  106, 'reports',     'create', 18, '2026-06-01'),
                (10, 107, 'settings',    'edit',    8, '2026-06-02'),
                (11, 108, 'dashboard',   'view',   56, '2026-06-01'),
                (12, 109, 'pipeline',    'view',    9, '2026-06-03'),
                (13, 110, 'reports',     'export', 28, '2026-06-01'),
                (14, 111, 'dashboard',   'create', 14, '2026-06-02'),
                (15, 112, 'pipeline',    'view',   71, '2026-06-01'),
                (16, 113, 'settings',    'export',  5, '2026-06-03'),
                (17, 114, 'dashboard',   'view',   33, '2026-06-01'),
                (18, 115, 'reports',     'create', 21, '2026-06-02'),
                (19, 101, 'settings',    'edit',   10, '2026-06-05'),
                (20, 102, 'dashboard',   'export', 44, '2026-06-05'),
                (21, 105, 'reports',     'view',   52, '2026-06-05'),
                (22, 106, 'pipeline',    'create', 27, '2026-06-06'),
                (23, 108, 'pipeline',    'edit',   39, '2026-06-06'),
                (24, 111, 'reports',     'export', 11, '2026-06-07'),
                (25, 112, 'dashboard',   'view',   63, '2026-06-07')
        """)

        con.execute("""
            CREATE OR REPLACE TABLE raw_billing_invoices (
                invoice_id INTEGER,
                account_id INTEGER,
                invoice_amount DECIMAL(12,2),
                invoice_date DATE,
                paid_date DATE,
                status VARCHAR
            )
        """)

        con.execute("""
            INSERT INTO raw_billing_invoices VALUES
                (1,  101, 12500.00, '2026-06-01', '2026-06-05', 'paid'),
                (2,  102, 45000.00, '2026-05-15', '2026-05-20', 'paid'),
                (3,  103, 8900.00,  '2026-06-01', NULL,         'pending'),
                (4,  104, 32000.00, '2026-05-01', '2026-05-10', 'paid'),
                (5,  105, 78000.00, '2026-06-01', '2026-06-03', 'paid'),
                (6,  106, 150000.00,'2026-06-01', '2026-06-08', 'paid'),
                (7,  107, 15000.00, '2026-05-20', '2026-05-25', 'paid'),
                (8,  108, 55000.00, '2026-06-01', NULL,         'overdue'),
                (9,  109, 4200.00,  '2026-06-01', '2026-06-02', 'paid'),
                (10, 110, 18000.00, '2026-05-10', '2026-05-15', 'paid'),
                (11, 111, 3500.00,  '2026-06-01', NULL,         'pending'),
                (12, 112, 110000.00,'2026-06-01', '2026-06-07', 'paid'),
                (13, 113, 2800.00,  '2026-05-05', '2026-05-10', 'paid'),
                (14, 114, 65000.00, '2026-06-01', '2026-06-04', 'paid'),
                (15, 115, 42000.00, '2026-05-25', '2026-05-30', 'paid'),
                (16, 101, 15000.00, '2026-07-01', NULL,         'pending'),
                (17, 105, 82000.00, '2026-07-01', '2026-07-03', 'paid'),
                (18, 106, 145000.00,'2026-07-01', NULL,         'pending'),
                (19, 112, 105000.00,'2026-07-01', '2026-07-06', 'paid'),
                (20, 114, 62000.00, '2026-07-01', '2026-07-04', 'paid')
        """)

        con.execute("""
            CREATE OR REPLACE TABLE raw_billing_subscriptions (
                subscription_id INTEGER,
                account_id INTEGER,
                plan_tier VARCHAR,
                monthly_price DECIMAL(10,2),
                start_date DATE,
                end_date DATE,
                is_active BOOLEAN
            )
        """)

        con.execute("""
            INSERT INTO raw_billing_subscriptions VALUES
                (1,  101, 'enterprise', 2500.00,  '2025-01-01', '2026-12-31', true),
                (2,  102, 'enterprise', 5000.00,  '2025-01-01', '2026-12-31', true),
                (3,  103, 'pro',        1200.00,  '2025-03-15', '2026-12-31', true),
                (4,  104, 'enterprise', 3500.00,  '2025-01-01', '2026-12-31', true),
                (5,  105, 'enterprise', 7500.00,  '2025-01-01', '2026-12-31', true),
                (6,  106, 'enterprise', 12000.00, '2025-01-01', '2026-12-31', true),
                (7,  107, 'pro',        1800.00,  '2025-06-01', '2026-05-31', false),
                (8,  108, 'enterprise', 6000.00,  '2025-01-01', '2026-12-31', true),
                (9,  109, 'starter',     400.00,  '2025-09-01', '2026-12-31', true),
                (10, 110, 'pro',        2200.00,  '2025-01-01', '2026-12-31', true),
                (11, 111, 'starter',     450.00,  '2025-04-01', '2026-12-31', true),
                (12, 112, 'enterprise', 10000.00, '2025-01-01', '2026-12-31', true),
                (13, 113, 'starter',     300.00,  '2025-07-01', '2026-06-30', false),
                (14, 114, 'enterprise', 6500.00,  '2025-01-01', '2026-12-31', true),
                (15, 115, 'enterprise', 4800.00,  '2025-01-01', '2026-12-31', true)
        """)

    print(f"Seeded 5 source tables into {DB_PATH}")


if __name__ == "__main__":
    main()
