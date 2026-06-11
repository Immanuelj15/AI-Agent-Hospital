# backend/db.py
import os
import sqlite3
import pandas as pd

DB_PATH = os.path.join("backend", "medicines.db")
CSV_PATH = "medicine_dataset.csv"

def get_db_connection():
    """Returns a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_dosage_instruction(dosage_form):
    """Generates realistic dosage instructions based on the dosage form."""
    form = str(dosage_form).lower()
    if "tablet" in form or "capsule" in form:
        return "Take 1 tablet/capsule daily after meals"
    elif "injection" in form:
        return "Must be administered by a healthcare professional"
    elif "syrup" in form or "drops" in form:
        return "Take 10ml twice a day or as directed by doctor"
    elif "cream" in form or "ointment" in form:
        return "Apply thinly to the affected area 2-3 times daily"
    elif "inhaler" in form:
        return "Inhale 2 puffs every 12 hours as needed"
    else:
        return "Take as directed by your physician"

def get_side_effects(category):
    """Generates realistic side effects based on the medicine category."""
    cat = str(category).lower()
    if "antidiabetic" in cat:
        return "Hypoglycemia, nausea, stomach upset, fatigue"
    elif "antiviral" in cat:
        return "Headache, muscle pain, tiredness, nausea"
    elif "antibiotic" in cat:
        return "Stomach cramps, diarrhea, mild rash, nausea"
    elif "antifungal" in cat:
        return "Mild stomach discomfort, local skin irritation"
    elif "antipyretic" in cat or "analgesic" in cat:
        return "Heartburn, stomach upset, mild headache"
    elif "antidepressant" in cat:
        return "Drowsiness, dry mouth, sleep changes, weight changes"
    elif "antiseptic" in cat:
        return "Skin dryness, mild skin irritation on application"
    else:
        return "Mild nausea, headache, dry mouth"

def rebuild_database():
    """Parses medicine_dataset.csv and builds an indexed SQLite database."""
    print("Initializing SQLite Database...")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    # Connect and clean up previous DB if any
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except Exception as e:
            print(f"Warning: Could not clear previous SQLite file: {e}")
            
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create the schema
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS medicines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        category TEXT,
        dosage_form TEXT,
        strength TEXT,
        manufacturer TEXT,
        indication TEXT,
        classification TEXT,
        price REAL,
        stock TEXT,
        dosage_instruction TEXT,
        side_effects TEXT
    )
    """)
    
    # Create indexes for fast search
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_name ON medicines(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_category ON medicines(category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_classification ON medicines(classification)")
    conn.commit()

    if not os.path.exists(CSV_PATH):
        print(f"Dataset file {CSV_PATH} not found!")
        conn.close()
        return False

    print(f"Reading dataset from {CSV_PATH}...")
    # Read CSV in chunks to handle memory safely
    chunksize = 10000
    total_loaded = 0
    
    for chunk in pd.read_csv(CSV_PATH, chunksize=chunksize):
        # Rename columns to ensure consistency
        chunk.columns = [c.strip() for c in chunk.columns]
        
        batch = []
        for idx, row in chunk.iterrows():
            name = str(row.get('Name', 'Unknown'))
            category = str(row.get('Category', 'General'))
            dosage_form = str(row.get('Dosage Form', 'Tablet'))
            strength = str(row.get('Strength', 'N/A'))
            manufacturer = str(row.get('Manufacturer', 'Unknown'))
            indication = str(row.get('Indication', 'General Care'))
            classification = str(row.get('Classification', 'Prescription'))
            
            # Enrich fields
            # Generate deterministic mock values based on properties
            stock = "Yes" if (hash(name) % 5 != 0) else "No"  # 80% stock rate
            
            # Derive price from strength numbers
            num_part = ''.join(filter(str.isdigit, strength))
            price_base = float(num_part) if num_part else 10.0
            price = round(min(max(price_base * 0.05, 1.50), 150.0), 2)  # Cap price between $1.50 and $150
            
            dosage_instruction = get_dosage_instruction(dosage_form)
            side_effects = get_side_effects(category)
            
            batch.append((
                name, category, dosage_form, strength, manufacturer, 
                indication, classification, price, stock, dosage_instruction, side_effects
            ))
            
        cursor.executemany("""
        INSERT INTO medicines (
            name, category, dosage_form, strength, manufacturer, 
            indication, classification, price, stock, dosage_instruction, side_effects
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, batch)
        conn.commit()
        total_loaded += len(batch)
        print(f"Loaded {total_loaded} records into SQLite database...")
        
    conn.close()
    print("SQLite database successfully populated and indexed.")
    return True

def search_medicines(search_str=None, category=None, classification=None, page=1, limit=50):
    """Executes a fast paginated, filtered SQL search on the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM medicines WHERE 1=1"
    count_query = "SELECT COUNT(*) FROM medicines WHERE 1=1"
    params = []
    
    if search_str:
        # Match name, category, or manufacturer
        query += " AND (name LIKE ? OR category LIKE ? OR manufacturer LIKE ?)"
        count_query += " AND (name LIKE ? OR category LIKE ? OR manufacturer LIKE ?)"
        like_param = f"%{search_str}%"
        params.extend([like_param, like_param, like_param])
        
    if category:
        query += " AND category = ?"
        count_query += " AND category = ?"
        params.append(category)
        
    if classification:
        query += " AND classification = ?"
        count_query += " AND classification = ?"
        params.append(classification)
        
    # Get total count first
    cursor.execute(count_query, params)
    total_count = cursor.fetchone()[0]
    
    # Add pagination
    query += " ORDER BY id ASC LIMIT ? OFFSET ?"
    offset = (page - 1) * limit
    params_with_paging = params + [limit, offset]
    
    cursor.execute(query, params_with_paging)
    rows = cursor.fetchall()
    
    # Convert Row objects to dicts
    medicines = [dict(row) for row in rows]
    
    # For out-of-stock items, dynamically suggest alternatives in same category
    for med in medicines:
        if med['stock'] == 'No':
            cursor.execute(
                "SELECT name, price FROM medicines WHERE category = ? AND stock = 'Yes' LIMIT 1",
                (med['category'],)
            )
            alt = cursor.fetchone()
            med['alternative'] = alt['name'] if alt else "Generic Substitute"
        else:
            med['alternative'] = "N/A"
            
    conn.close()
    return medicines, total_count

def get_stats():
    """Generates statistics from the medicine table for dashboard metrics."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Total Medicines
    cursor.execute("SELECT COUNT(*) FROM medicines")
    total_count = cursor.fetchone()[0]
    
    if total_count == 0:
        conn.close()
        return {"total": 0, "categories": [], "classifications": {}, "manufacturers": []}
        
    # 2. Classification Split
    cursor.execute("SELECT classification, COUNT(*) FROM medicines GROUP BY classification")
    classifications = {row[0]: row[1] for row in cursor.fetchall()}
    
    # 3. Top Categories
    cursor.execute("SELECT category, COUNT(*) as count FROM medicines GROUP BY category ORDER BY count DESC LIMIT 5")
    categories = [{"category": row[0], "count": row[1]} for row in cursor.fetchall()]
    
    # 4. Top Manufacturers
    cursor.execute("SELECT manufacturer, COUNT(*) as count FROM medicines GROUP BY manufacturer ORDER BY count DESC LIMIT 5")
    manufacturers = [{"manufacturer": row[0], "count": row[1]} for row in cursor.fetchall()]
    
    conn.close()
    return {
        "total": total_count,
        "categories": categories,
        "classifications": classifications,
        "manufacturers": manufacturers
    }

if __name__ == "__main__":
    rebuild_database()
    print("Testing search...")
    res, count = search_medicines(search_str="Amoxicillin", limit=5)
    print(f"Found {count} matches:")
    for r in res:
        print(f"Name: {r['name']}, Category: {r['category']}, Form: {r['dosage_form']}, Stock: {r['stock']}, Alt: {r['alternative']}")
