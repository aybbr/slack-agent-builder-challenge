from pathlib import Path

import duckdb

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = str(DATA_DIR / "demo.duckdb")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(DB_PATH) as con:
        con.execute("""
            CREATE OR REPLACE TABLE raw_salesforce_opportunity (
                opportunity_id INTEGER,
                customer_id INTEGER,
                amount DECIMAL(12,2),
                stage VARCHAR,
                lead_score INTEGER,
                close_date DATE,
                created_at DATE
            )
        """)

        con.execute("""
            INSERT INTO raw_salesforce_opportunity VALUES
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
                (14, 105, 175000.00, 'closed_won',      88, '2026-05-01', '2025-12-20')
        """)

        con.execute("""
            CREATE OR REPLACE TABLE raw_finance_revenue (
                opportunity_id INTEGER,
                revenue_amount DECIMAL(12,2),
                recognition_date DATE
            )
        """)

        con.execute("""
            INSERT INTO raw_finance_revenue VALUES
                (1,  42000.00, '2026-04-01'),
                (2,  98000.00, '2026-07-15'),
                (3,  60000.00, '2026-06-01'),
                (4,  72000.00, '2026-09-01'),
                (5,  0.00,     '2026-05-01'),
                (6,  175000.00,'2026-08-01'),
                (7,  38000.00, '2026-10-01'),
                (8,  50000.00, '2026-07-01'),
                (9,  130000.00,'2026-03-15'),
                (10, 68000.00, '2026-11-01'),
                (11, 32000.00, '2026-09-15'),
                (12, 90000.00, '2026-08-01'),
                (13, 28000.00, '2026-12-01'),
                (14, 145000.00,'2026-06-01')
        """)

        con.execute("""
            CREATE OR REPLACE TABLE raw_customer (
                customer_id INTEGER,
                customer_name VARCHAR,
                industry VARCHAR,
                region VARCHAR
            )
        """)

        con.execute("""
            INSERT INTO raw_customer VALUES
                (101, 'Acme Corp',         'Manufacturing', 'North America'),
                (102, 'Globex Industries', 'Technology',    'Europe'),
                (103, 'Initech Solutions', 'Finance',       'Asia Pacific'),
                (104, 'Umbrella Holdings', 'Healthcare',    'North America'),
                (105, 'Stark Enterprises', 'Technology',    'Europe'),
                (106, 'Wayne Enterprises', 'Defense',       'North America'),
                (107, 'Oscorp Industries', 'Chemicals',     'Asia Pacific'),
                (108, 'LexCorp',           'Energy',        'Europe'),
                (109, 'Vandelay Industries','Manufacturing','North America'),
                (110, 'Wonka Industries',  'Food & Beverage','Europe')
        """)

    print(f"Seeded source tables into {DB_PATH}")


if __name__ == "__main__":
    main()
