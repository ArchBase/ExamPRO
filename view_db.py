import sqlite3
import pandas as pd

def export_database_to_excel(db_path, excel_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    # Create a Pandas Excel writer
    with pd.ExcelWriter(excel_path, engine='xlsxwriter') as writer:
        for table in tables:
            table_name = table[0]
            
            # Fetch data into a Pandas DataFrame
            df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
            
            # Write DataFrame to an Excel sheet
            df.to_excel(writer, sheet_name=table_name, index=False)
    
    conn.close()
    print(f"Database contents exported to {excel_path}")

# Example usage:
db_path = "database.db"  # Replace with your SQLite database path
excel_path = "database_contents.xlsx"  # Output Excel file
export_database_to_excel(db_path, excel_path)
