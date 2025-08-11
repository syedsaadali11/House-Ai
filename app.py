from flask import Flask, request, jsonify, render_template, send_from_directory, redirect
import os
import logging
import pandas as pd
import numpy as np
import random
# Fix for Windows OMP error
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Initialize Flask app
app = Flask(__name__, template_folder='pages', static_folder='static')
# ✅ Load LangGraph Agent ONCE at startup
try:
    from backend.agents.rental_agent.graph import create_agent
    run_rental_agent = create_agent()
    logger.info("✅ LangGraph agent compiled successfully and ready to use")
except Exception as e:
    logger.critical(f"❌ Failed to load agent: {e}")
    raise RuntimeError("Agent failed to load. Check backend/agents/rental_agent/graph.py") from e

# --- Routes ---
# Serve HTML pages
@app.route("/")
def home():
    return render_template("index.html")

# Handle index.html explicitly - redirect to /
@app.route("/index.html")
def index_html():
    return redirect("/")

# 🔧 FIX: Handle property-detail route specifically
@app.route("/property-detail")
def property_detail():
    # The HTML file will handle getting the ID from URL params via JavaScript
    return render_template("property-detail.html")

# Handle both with and without .html extension
@app.route("/<page>")
@app.route("/<page>.html")
def serve_page(page):
    valid_pages = ["auth", "upload", "dashboard-renter", "dashboard-owner"]
    # Remove .html extension if present
    if page.endswith('.html'):
        page = page[:-5]
    if page in valid_pages:
        return render_template(f"{page}.html")
    return "<h1>404 – Page Not Found</h1><p><a href='/'>← Back to Home</a></p>", 404

# API: Ask AI for rental recommendations
@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json()
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "Query is required"}), 400
    try:
        # Initialize state with all required fields
        initial_state = {
            "query": query,
            "extracted_filters": {},
            "semantic_query": query,
            "filtered_meta": pd.DataFrame(),
            "matches": [],
            "response": "",
            "messages": []
        }
        
        # Run agent
        result = run_rental_agent.invoke(initial_state)
        response_text = result.get("response", "No response from AI.")
        return jsonify({"response": response_text})
    except Exception as e:
        logger.error(f"AI Agent Error: {str(e)}")
        return jsonify({
            "response": "❌ Sorry, I couldn't process your request. Please try again."
        }), 500

# API: User Registration
@app.route("/api/register", methods=["POST"])
def register_user():
    try:
        data = request.get_json()
        full_name = data.get("full_name")
        email = data.get("email")
        phone = data.get("phone")
        password = data.get("password")
        user_type = data.get("user_type")
        
        # Validate required fields
        if not all([full_name, email, phone, password, user_type]):
            return jsonify({"error": "Missing required fields"}), 400
            
        # Load users from CSV (or create if doesn't exist)
        data_dir = os.path.join(os.getcwd(), "data")
        users_csv_path = os.path.join(data_dir, "users.csv")
        
        if os.path.exists(users_csv_path):
            users_df = pd.read_csv(users_csv_path)
        else:
            users_df = pd.DataFrame(columns=["id", "full_name", "email", "phone", "password", "user_type", "created_at"])
        
        # Check if email already exists
        if email in users_df['email'].values:
            return jsonify({"error": "Email already registered"}), 400
            
        # Generate new ID
        new_id = len(users_df) + 1
        
        # Add new user
        new_row = {
            "id": new_id,
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "password": password,  # In production, hash this password
            "user_type": user_type,
            "created_at": pd.Timestamp.now().isoformat()
        }
        new_df = pd.DataFrame([new_row])
        users_df = pd.concat([users_df, new_df], ignore_index=True)
        users_df.to_csv(users_csv_path, index=False)
        
        return jsonify({
            "message": "✅ Registration successful!",
            "user": {
                "id": new_id,
                "full_name": full_name,
                "email": email,
                "user_type": user_type
            }
        })
    
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return jsonify({"error": "Registration failed. Please try again."}), 500

# API: User Login
@app.route("/api/login", methods=["POST"])
def login_user():
    try:
        data = request.get_json()
        email = data.get("email")
        password = data.get("password")
        
        # Validate required fields
        if not all([email, password]):
            return jsonify({"error": "Email and password are required"}), 400
            
        # Load users from CSV
        data_dir = os.path.join(os.getcwd(), "data")
        users_csv_path = os.path.join(data_dir, "users.csv")
        
        if not os.path.exists(users_csv_path):
            return jsonify({"error": "No users found. Please register first."}), 404
            
        users_df = pd.read_csv(users_csv_path)
        
        # Find user with matching email and password
        user = users_df[(users_df['email'] == email) & (users_df['password'] == password)]
        
        if user.empty:
            return jsonify({"error": "Invalid email or password"}), 401
            
        user_data = user.iloc[0].to_dict()
        
        return jsonify({
            "message": "✅ Login successful!",
            "user": {
                "id": user_data["id"],
                "full_name": user_data["full_name"],
                "email": user_data["email"],
                "user_type": user_data["user_type"]
            }
        })
    
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({"error": "Login failed. Please try again."}), 500

# API: Upload property listing
@app.route("/api/upload-property", methods=["POST"])
def upload_property():
    try:
        # Get all form fields
        city = request.form.get("city")
        area = request.form.get("area")
        size_marla = request.form.get("size_marla")
        stories = request.form.get("stories")
        bedrooms = request.form.get("bedrooms")
        price = request.form.get("price")
        bathrooms = request.form.get("bathrooms")
        electricity = request.form.get("electricity")
        gas = request.form.get("gas")
        location = request.form.get("location")
        status = request.form.get("status", "available")  # Default to available if not provided
        
        # Validate required fields
        if not all([city, area, size_marla, stories, bedrooms, price, bathrooms, electricity, gas, location]):
            return jsonify({"error": "Missing required fields"}), 400
            
        # Validate numeric values
        try:
            size_marla = float(size_marla)
            price = int(price)
            bedrooms = int(bedrooms)
            bathrooms = int(bathrooms)
        except ValueError:
            return jsonify({"error": "Invalid numeric values"}), 400
            
        # Validate text fields
        if len(city.strip()) < 2 or len(area.strip()) < 2:
            return jsonify({"error": "City and area must be at least 2 characters long"}), 400
            
        # Load CSV
        data_dir = os.path.join(os.getcwd(), "data")
        csv_path = os.path.join(data_dir, "rental_metadata_90k.csv")
        
        if not os.path.exists(csv_path):
            return jsonify({"error": "Data file not found. Please run preprocessing first."}), 500
            
        metadata = pd.read_csv(csv_path)
        
        # Check if status column exists, if not add it
        if 'status' not in metadata.columns:
            metadata['status'] = 'available'
            
        # Generate new ID
        new_id = len(metadata) + 1
        
        # Create text field in the same format as synthetic data
        text = f"A {size_marla} marla {stories}-story house in {area.strip()}, {city.strip()} with {bedrooms} bedrooms, {bathrooms} bathrooms, electricity: {electricity}, gas: {gas}. Located near {location}. Rent: {price} PKR. Status: {status}."
        
        # Add to CSV
        new_row = {
            "id": new_id,
            "city": city.strip(),
            "area": area.strip(),
            "size_marla": size_marla,
            "stories": stories,
            "bedrooms": bedrooms,
            "price": price,
            "bathrooms": bathrooms,
            "electricity": electricity,
            "gas": gas,
            "location": location,
            "status": status,
            "text": text
        }
        
        new_df = pd.DataFrame([new_row])
        metadata = pd.concat([metadata, new_df], ignore_index=True)
        metadata.to_csv(csv_path, index=False)
        
        # ✅ UPDATE FAISS INDEX WITH NEW PROPERTY
        try:
            from backend.faiss_update import update_faiss_with_new_property
            update_faiss_with_new_property(new_row)
            logger.info(f"✅ FAISS updated with new property ID: {new_id}")
        except Exception as e:
            logger.warning(f"⚠️ FAISS update failed: {e}")
            
        return jsonify({
            "message": "✅ Your property has been listed successfully!",
            "data": {
                "id": new_id,
                "city": city.strip(),
                "area": area.strip(),
                "size_marla": size_marla,
                "price": price,
                "status": status
            }
        })
    
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return jsonify({"error": "Upload failed. Please try again."}), 500

# API: Get owner's properties
@app.route("/api/owner/properties", methods=["GET"])
def get_owner_properties():
    try:
        # Load CSV
        data_dir = os.path.join(os.getcwd(), "data")
        csv_path = os.path.join(data_dir, "rental_metadata_90k.csv")
        
        if not os.path.exists(csv_path):
            return jsonify({"error": "Data file not found"}), 500
            
        metadata = pd.read_csv(csv_path)
        
        # For demo purposes, return all properties
        # In a real app, you would filter by owner ID
        properties = metadata.to_dict('records')
        
        # Add image URLs for display
        for prop in properties:
            prop['image'] = f"https://images.unsplash.com/photo-1600585154340-be6161a56a0c?ixlib=rb-4.0.3&auto=format&fit=crop&w=600&q=80"
            # Add status class for UI
            prop['statusClass'] = "bg-green-100 text-green-800" if prop.get('status', 'available') == 'available' else "bg-red-100 text-red-800"
            prop['statusIcon'] = "check-circle" if prop.get('status', 'available') == 'available' else "home"
            prop['status'] = prop.get('status', 'available').title()
        
        return jsonify(properties)
    except Exception as e:
        logger.error(f"Error fetching properties: {str(e)}")
        return jsonify({"error": "Failed to fetch properties"}), 500

# API: Update property status
@app.route("/api/property/<int:property_id>/status", methods=["PUT"])
def update_property_status(property_id):
    try:
        data = request.get_json()
        new_status = data.get("status")
        
        if new_status not in ["available", "rented"]:
            return jsonify({"error": "Invalid status value"}), 400
            
        # Load CSV
        data_dir = os.path.join(os.getcwd(), "data")
        csv_path = os.path.join(data_dir, "rental_metadata_90k.csv")
        
        if not os.path.exists(csv_path):
            return jsonify({"error": "Data file not found"}), 500
            
        metadata = pd.read_csv(csv_path)
        
        # Find property by ID
        property_index = metadata.index[metadata['id'] == property_id].tolist()
        
        if not property_index:
            return jsonify({"error": "Property not found"}), 404
            
        property_index = property_index[0]
        
        # Update status
        metadata.at[property_index, 'status'] = new_status
        
        # Update text field to reflect new status
        prop = metadata.iloc[property_index]
        metadata.at[property_index, 'text'] = f"A {prop['size_marla']} marla {prop['stories']}-story house in {prop['area']}, {prop['city']} with {prop['bedrooms']} bedrooms, {prop['bathrooms']} bathrooms, electricity: {prop['electricity']}, gas: {prop['gas']}. Located near {prop['location']}. Rent: {prop['price']} PKR. Status: {new_status}."
        
        # Save updated CSV
        metadata.to_csv(csv_path, index=False)
        
        # Update FAISS index
        try:
            from backend.faiss_update import rebuild_faiss_index
            rebuild_faiss_index()
            logger.info(f"✅ FAISS index rebuilt after status update for property ID: {property_id}")
        except Exception as e:
            logger.warning(f"⚠️ FAISS update failed: {e}")
        
        return jsonify({"message": "Property status updated successfully"})
    except Exception as e:
        logger.error(f"Error updating property status: {str(e)}")
        return jsonify({"error": "Failed to update property status"}), 500

# Serve static files
@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)

# Serve data files (CSV, JSON, embeddings)
@app.route("/data/<path:filename>")
def data_files(filename):
    data_dir = os.path.join(os.getcwd(), "data")
    file_path = os.path.join(data_dir, filename)
    
    if not os.path.exists(file_path):
        logger.error(f"Data file not found: {file_path}")
        return "File not found", 404
    
    logger.info(f"✅ Serving data file: {filename}")
    return send_from_directory(data_dir, filename)

# --- Run Server ---
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 HOUSE AI SERVER - RUNNING NOW")
    print("💡 Access: http://localhost:5000")
    print("📱 Renter: http://localhost:5000/dashboard-renter")
    print("🏠 Owner: http://localhost:5000/upload")
    print("🔧 Agent is loaded: ✅")
    print("📁 FAISS index auto-updates: ✅")
    print("="*60 + "\n")
    
    app.run(debug=True, host="0.0.0.0", port=5000)