#!/usr/bin/env python3
# Fix the missing category column in the database

import sqlite3
import os

def fix_category_column():
    # Path to your database
    db_path = "frontend/instance/yourdb.db"
    
    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        return
    
    print(f"Connecting to database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check current table structure
        cursor.execute("PRAGMA table_info(entries);")
        columns = [col[1] for col in cursor.fetchall()]
        print(f"Current columns: {columns}")
        
        # Add category column if it doesn't exist
        if 'category' not in columns:
            print("Adding category column...")
            cursor.execute("ALTER TABLE entries ADD COLUMN category TEXT DEFAULT 'other';")
            
            # Update existing entries
            cursor.execute("UPDATE entries SET category = 'other' WHERE category IS NULL;")
            
            print("Category column added successfully!")
            print(f"Updated {cursor.rowcount} rows")
        else:
            print("Category column already exists!")
        
        conn.commit()
        
        # Verify the fix
        cursor.execute("SELECT COUNT(*) FROM entries;")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM entries WHERE category IS NOT NULL;")
        with_category = cursor.fetchone()[0]
        
        print(f"Total entries: {total}")
        print(f"Entries with category: {with_category}")
        
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    fix_category_column()
