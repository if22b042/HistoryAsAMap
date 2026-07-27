"""
Migration script for PostgreSQL to add lat and lon columns to locations table
and populate them from the existing coordinates string.
"""
import os
import psycopg2
from urllib.parse import urlparse
from dotenv import load_dotenv

# Load environment variables from .env.production file
load_dotenv('.env.production')

def get_database_url():
    """Get the production database URL from environment variables."""
    # Vercel provides DATABASE_URL or individual PostgreSQL variables
    database_url = os.environ.get('DATABASE_URL')
    
    if not database_url:
        # Try to construct from individual variables
        pguser = os.environ.get('PGUSER') or os.environ.get('POSTGRES_USER')
        pgpassword = os.environ.get('PGPASSWORD') or os.environ.get('POSTGRES_PASSWORD')
        pghost = os.environ.get('PGHOST') or os.environ.get('POSTGRES_HOST')
        pgdatabase = os.environ.get('PGDATABASE') or os.environ.get('POSTGRES_DATABASE')
        
        if pguser and pgpassword and pghost and pgdatabase:
            database_url = f"postgresql://{pguser}:{pgpassword}@{pghost}/{pgdatabase}"
    
    return database_url

def migrate_locations():
    """Migrate existing locations to have lat and lon fields in PostgreSQL."""
    
    db_url = get_database_url()
    if not db_url:
        print("ERROR: DATABASE_URL environment variable not set")
        print("Please set DATABASE_URL to your PostgreSQL connection string")
        return
    
    print(f"Connecting to database...")
    
    try:
        # Parse the connection string
        parsed = urlparse(db_url)
        
        conn = psycopg2.connect(
            dbname=parsed.path[1:],  # Remove leading /
            user=parsed.username,
            password=parsed.password,
            host=parsed.hostname,
            port=parsed.port
        )
        
        conn.autocommit = False
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'locations' 
            AND column_name IN ('lat', 'lon')
        """)
        existing_columns = [row[0] for row in cursor.fetchall()]
        
        print(f"Existing columns: {existing_columns}")
        
        # Add lat column if it doesn't exist
        if 'lat' not in existing_columns:
            print("Adding lat column...")
            cursor.execute("ALTER TABLE locations ADD COLUMN lat REAL")
            print("✓ Added lat column")
        else:
            print("lat column already exists")
        
        # Add lon column if it doesn't exist
        if 'lon' not in existing_columns:
            print("Adding lon column...")
            cursor.execute("ALTER TABLE locations ADD COLUMN lon REAL")
            print("✓ Added lon column")
        else:
            print("lon column already exists")
        
        conn.commit()
        
        # Populate lat and lon from coordinates string
        print("\nPopulating lat and lon from coordinates...")
        cursor.execute("""
            SELECT id, coordinates 
            FROM locations 
            WHERE coordinates IS NOT NULL 
            AND (lat IS NULL OR lon IS NULL)
        """)
        
        locations = cursor.fetchall()
        print(f"Found {len(locations)} locations to migrate")
        
        updated_count = 0
        error_count = 0
        
        for location_id, coordinates in locations:
            try:
                # Parse coordinates string (format: "lat,lon")
                coords = coordinates.split(',')
                if len(coords) == 2:
                    lat = float(coords[0].strip())
                    lon = float(coords[1].strip())
                    
                    cursor.execute("""
                        UPDATE locations 
                        SET lat = %s, lon = %s 
                        WHERE id = %s
                    """, (lat, lon, location_id))
                    
                    updated_count += 1
                    print(f"✓ Updated location {location_id}: {lat}, {lon}")
            except Exception as e:
                error_count += 1
                print(f"✗ Error migrating location {location_id}: {e}")
        
        conn.commit()
        
        # Also update coordinates string if lat/lon exist but coordinates doesn't
        print("\nUpdating coordinates string from lat/lon where missing...")
        cursor.execute("""
            SELECT id, lat, lon 
            FROM locations 
            WHERE (lat IS NOT NULL AND lon IS NOT NULL) 
            AND coordinates IS NULL
        """)
        
        locations_needing_coords = cursor.fetchall()
        print(f"Found {len(locations_needing_coords)} locations needing coordinates string")
        
        for location_id, lat, lon in locations_needing_coords:
            try:
                coordinates_str = f"{lat},{lon}"
                cursor.execute("""
                    UPDATE locations 
                    SET coordinates = %s 
                    WHERE id = %s
                """, (coordinates_str, location_id))
                
                updated_count += 1
                print(f"✓ Updated coordinates for location {location_id}: {coordinates_str}")
            except Exception as e:
                error_count += 1
                print(f"✗ Error updating coordinates for location {location_id}: {e}")
        
        conn.commit()
        
        print(f"\n{'='*50}")
        print(f"Migration complete!")
        print(f"Updated: {updated_count} locations")
        print(f"Errors: {error_count} locations")
        print(f"{'='*50}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"ERROR: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        raise

if __name__ == "__main__":
    migrate_locations()
