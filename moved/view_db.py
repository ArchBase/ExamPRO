import sqlite3

def print_database_contents(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    for table in tables:
        table_name = table[0]
        print(f"\nTable: {table_name}")
        print("=" * (len(table_name) + 8))
        
        # Fetch all data from the table
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        
        # Fetch column names
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [col[1] for col in cursor.fetchall()]
        print(" | ".join(columns))
        print("-" * (len(" | ".join(columns))))
        
        # Print each row
        for row in rows:
            print(" | ".join(str(item) for item in row))
    
    conn.close()

# Example usage:
db_path = "database.db"  # Replace with your SQLite database path
print_database_contents(db_path)
