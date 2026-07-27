"""
Migration route to add lat and lon columns to locations table
"""
from flask import Blueprint, jsonify
from sqlalchemy import text
from backend.models.model import db, Location

migration_bp = Blueprint('migration', __name__)

@migration_bp.route('/run-migration', methods=['POST'])
def run_migration():
    """Run the database migration to add lat and lon columns."""
    
    try:
        # Check if columns already exist
        result = db.session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'locations' 
            AND column_name IN ('lat', 'lon')
        """))
        existing_columns = [row[0] for row in result]
        
        # Add lat column if it doesn't exist
        if 'lat' not in existing_columns:
            db.session.execute(text("ALTER TABLE locations ADD COLUMN lat REAL"))
        
        # Add lon column if it doesn't exist
        if 'lon' not in existing_columns:
            db.session.execute(text("ALTER TABLE locations ADD COLUMN lon REAL"))
        
        db.session.commit()
        
        # Populate lat and lon from coordinates string
        result = db.session.execute(text("""
            SELECT id, coordinates 
            FROM locations 
            WHERE coordinates IS NOT NULL 
            AND (lat IS NULL OR lon IS NULL)
        """))
        
        locations = result.fetchall()
        
        updated_count = 0
        error_count = 0
        
        for location_id, coordinates in locations:
            try:
                # Parse coordinates string (format: "lat,lon")
                coords = coordinates.split(',')
                if len(coords) == 2:
                    lat = float(coords[0].strip())
                    lon = float(coords[1].strip())
                    
                    db.session.execute(text("""
                        UPDATE locations 
                        SET lat = :lat, lon = :lon 
                        WHERE id = :id
                    """), {'lat': lat, 'lon': lon, 'id': location_id})
                    
                    updated_count += 1
            except Exception as e:
                error_count += 1
        
        db.session.commit()
        
        # Also update coordinates string if lat/lon exist but coordinates doesn't
        result = db.session.execute(text("""
            SELECT id, lat, lon 
            FROM locations 
            WHERE (lat IS NOT NULL AND lon IS NOT NULL) 
            AND coordinates IS NULL
        """))
        
        locations_needing_coords = result.fetchall()
        
        for location_id, lat, lon in locations_needing_coords:
            try:
                coordinates_str = f"{lat},{lon}"
                db.session.execute(text("""
                    UPDATE locations 
                    SET coordinates = :coordinates 
                    WHERE id = :id
                """), {'coordinates': coordinates_str, 'id': location_id})
                
                updated_count += 1
            except Exception as e:
                error_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Migration completed successfully',
            'updated': updated_count,
            'errors': error_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
