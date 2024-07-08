from flask import Flask, jsonify, request
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore
from openai import OpenAI
from dotenv import load_dotenv
import json
import re
import os
import requests
from urllib.parse import urlencode

import logging
# Connect to openAI API
load_dotenv()
api_key = os.getenv('OPENAI_API_KEY')
if api_key is None:
    raise ValueError("OpenAI API key not found in environment variables.")
client = OpenAI(api_key=api_key)
# app = Flask(__name__, static_folder='../../CUSTOM-CLOSET-APP/public')
app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = '/home/aronott/Custom-Closet_App-Backend/static/uploads/'
#app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'static/uploads')

# Use the path to your service account JSON file
cred_path= os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred)

server_route = os.getenv('SERVER_ROUTE')

# Get a Firestore client
db = firestore.client()


# Configure upload folder
# UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
# if not os.path.exists(UPLOAD_FOLDER):
#     os.makedirs(UPLOAD_FOLDER)


# Setup logging
# Logging configuration
# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', handlers=[
    logging.FileHandler("/home/aronott/app.log"),  # For PythonAnywhere
    logging.StreamHandler()
])


# Initial log message to verify logging is working
logging.info("Application started")
@app.route('/pyament-success')
def payment_success():
     return jsonify({"message": "Payment successful and order stored"}), 200
@app.route('/pyament-error')
def payment_error():
     return jsonify({"message": "Payment failed"}), 200

@app.route('/payment-indicator', methods=['GET'])
def payment_indicator():
    logging.info('trigger indicator end point')
    data = request.form
    logging.info("Received data: %s", data)
    low_profile_code = request.args.get('lowprofilecode')
    status = request.args.get('OperationResponse')



    logging.info("LowProfileCode: %s, OperationResponse: %s", low_profile_code, status)

    if low_profile_code is None or status is None:
        logging.error("Missing LowProfileCode or OperationResponse")
        return jsonify({'status': 'error', 'message': 'Missing parameters'}), 400

    if status == '0' or status == 0:  # Assuming '0' means payment was successful
        logging.info("Payment successful for LowProfileCode: %s", low_profile_code)
        try:
            # Query for the document with the given low_profile_code as orderId
            orders_ref = db.collection('orders')
            query = orders_ref.where('orderId', '==', low_profile_code).stream()

            doc_found = False
            for doc in query:
                doc_ref = orders_ref.document(doc.id)
                doc_ref.set({'paid': True}, merge=True)
                logging.info("Database updated successfully for document ID: %s", doc.id)
                doc_found = True

            if not doc_found:
                logging.warning("No document found for LowProfileCode: %s", low_profile_code)
                return jsonify({'status': 'error', 'message': 'o document found for LowProfileCode'}), 500

        except Exception as e:
            logging.error("Failed to update database for LowProfileCode: %s, error: %s", low_profile_code, str(e))
            return jsonify({'status': 'error', 'message': 'Database update failed'}), 500
    else:
        logging.warning("Payment failed for LowProfileCode: %s", low_profile_code)

    return jsonify({'status': 'ok'}), 200

@app.post('/upload_img')
def upload_file():
    logging.debug("Received file upload request")
    if 'file' not in request.files:
        return jsonify({'msg': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'msg': 'No selected file'}), 400
    if file:
        filename = file.filename
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        logging.debug(f"Saving file to {file_path}")
        file.save(file_path)
        collection_ref = db.collection("uploads")
        doc_ref = collection_ref.add({
            'path': f'/static/uploads/{filename}'
        })

        # Update the return URL to reflect the actual server's URL
        return jsonify({'msg': 'File uploaded!', 'file': f'{server_route}/static/uploads/{filename}', 'id': doc_ref[1].id}), 200



@app.get('/uploads')
def test_get_images():
    logging.debug("Received request for test image list")
    try:
        images_ref = db.collection('uploads')
        docs = images_ref.stream()
        data = [{"id": doc.id, **doc.to_dict()} for doc in docs]
        updated_data = []
        for item in data:
            if 'price' in item:
                updated_data.append({"path": f'{server_route}{item["path"]}', "id": item['id'], "price": item['price']})
            else:
                updated_data.append({"path": f'{server_route}{item["path"]}', "id": item['id']})

        return jsonify({"data": updated_data})

    except Exception as e:
        logging.error(f"Error fetching images: {e}")
        return jsonify({'msg': 'Error fetching images'}), 500





@app.put("/uploads/<document_id>")
def update_price(document_id):
    data = request.json
    collection_ref = db.collection("uploads")
    document_ref = collection_ref.document(document_id)
    document_ref.update(data)

    doc = document_ref.get()
    path = f'{server_route}{doc._data["path"]}'
    price = doc._data["price"]

    return jsonify({"id": doc.id, "path": path, "price": price}), 200

@app.delete("/uploads/<document_id>")
def delete_img(document_id):
    try:
        collection_ref = db.collection("uploads")
        document_ref = collection_ref.document(document_id)
        doc = document_ref.get()

        if doc.exists:
            file_path = doc.to_dict().get('path')
            if file_path:
                # Construct the full path correctly using UPLOAD_FOLDER config
                full_path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(file_path))

                # Delete the document from Firestore
                document_ref.delete()

                # Delete the file from the filesystem
                if os.path.exists(full_path):
                    os.remove(full_path)
                    return jsonify({'message': 'Document and file deleted successfully'}), 200
                else:
                    return jsonify({'message': 'Document deleted but file not found'}), 404
            else:
                return jsonify({'message': 'File path not found in document'}), 400
        else:
            return jsonify({'message': 'Document not found'}), 404

    except Exception as e:
        logging.error(f"Error deleting document and file: {e}")
        return jsonify({'error': str(e)}), 500

# @app.route('/uploads/<filename>')
# def uploaded_file(filename):
#     logging.debug(f"Received request for file {filename}")
#     return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route("/")

def get_data():
    data = {"message": "This is JSON data from the server!"}
    return jsonify(data)
@app.route("/<name>")
def hello(name):
    return f"Hello, {name}!"

@app.route("/stocks")
def get_stocks():
    collection_ref = db.collection("stocks")
    docs = collection_ref.stream()
    data = [{"id": doc.id, **doc.to_dict()} for doc in docs]
    return jsonify({"data": data})

@app.route('/stocks/<name>')
def get_stock_by_name(name):
    try:
        collection_ref = db.collection("stocks")
        query_ref = collection_ref.where('name', '==', name).stream()
        results = [{"id": doc.id, **doc.to_dict()} for doc in query_ref]

        if results:
            return jsonify({"data": results}), 200
        else:
            return jsonify({"message": "No matching documents found"}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.post("/stocks")
def add_new_field():
    collection_ref = db.collection("stocks")
    data = request.json
    collection_ref.add(data)
    return jsonify({"message": "document successfully added"}),201

@app.put("/stocks/<document_id>")
def update_field(document_id):
    data = request.json
    collection_ref = db.collection("stocks")
    document_ref = collection_ref.document(document_id)
    document_ref.update(data)
    print(document_ref.get().id)
    print(document_ref.get()._data)
    return jsonify({"id": document_ref.get().id,**document_ref.get()._data}),200

@app.delete("/stocks/<document_id>")
def delete_field(document_id):
    collection_ref = db.collection("stocks")
    document_ref = collection_ref.document(document_id)
    document_ref.delete()
    return jsonify({"message": "document successfully deleted"}),200

@app.post('/orders')
def add_new_order():
    collection_ref = db.collection("orders")
    data = request.json
    collection_ref.add(data)
    return jsonify({"message": "document successfully added"}),201

@app.route("/orders")
def get_orders():
    collection_ref = db.collection("orders")
    query = collection_ref.where('paid', '==', True).stream()
    data = [{"id": doc.id, **doc.to_dict()} for doc in query]
    return jsonify({"data": data})

@app.delete("/orders/<document_id>")
def delete_order(document_id):
    collection_ref = db.collection("orders")
    document_ref = collection_ref.document(document_id)
    document_ref.delete()
    return jsonify({"message": "document successfully deleted"}),200

@app.route("/homePage")
def get_home_page_data():
    home_page_ref = db.collection("homePage")
    home_page_docs = home_page_ref.stream()
    img_ref = db.collection("uploads")
    img_docs = list(img_ref.stream())
    img_data = [{"id": doc.id, **doc.to_dict()} for doc in img_docs]
    data = {}
    data['text_content'] = [{"id": doc.id, **doc.to_dict()} for doc in home_page_docs]
    data['images'] = []
    for item in img_data:
        if 'price' in item:
            data['images'].append({"path": f'{server_route}{item["path"]}', "id": item['id'], "price": item['price']})
        else:
            data['images'].append({"path": f'{server_route}{item["path"]}', "id": item['id']})

    return jsonify({"data": data})


@app.put("/homePage/<document_id>")
def update_home_page_field(document_id):
    data = request.json
    collection_ref = db.collection("homePage")
    document_ref = collection_ref.document(document_id)
    document_ref.update(data)
    print(document_ref.get().id)
    print(document_ref.get()._data)
    return jsonify({"id": document_ref.get().id,**document_ref.get()._data}),200

@app.post("/ai")
def chat():
    user_message = request.json.get("text")

    messages = [
        {
            "role": "system",
            "content": """You help a cabinet design company. The company's cabinets are built from rectangular "cells" of different sizes. The user will provide you with the size of the closet he wants and you have to design a beautiful and special closet for him (according to the sizes that the user gave you) according to the following rules: Your answer should always be in dictionary (python) format, don't add any additional text,
                        Please provide the cabinet design specifications in the following format: {0: [{position: [x1, y1, z], size: [x1_length, y1_hight]}, {position: [x2, y2, z], size: [x2_length, y2_hight]} ...], 1: [{position: [x1, y1, z], size: [x1_length, y1_hight]}, {position: [x2, y2, z], size: [x2_length, y2_hight]} ...], ...},
                        where each key represents a layer (floor in the closet) and the value is this: the "position" key is a list of coordinates representing the position of the CENTER of the cube in that layer and the "size" key represent the width and the hight of each cube.
                        The Z coordinate is always 0! The position of the center of the first cube at key 0 must be [0, -1, 0]. The cabinets consist of "parts" in sizes 1 meters, 2 meter and 3 meters.
                        The "y_hight" value of each cube must be 1. Therfore, the "size" key will always be [x_length, 1] and the "y" value of the "position" key will always be the layer number minus 1.
                        For example: Let's say the sizes the user gave us are 3 meters high and 4 meters wide, an example of a valid response is: {0: [{position: [0, -1, 0], size: [1, 1]}, {position: [1.5, -1, 0], size: [2, 1]}, {position: [3, -1, 0], size: [1, 1]}], 1: [{position: [0.5, 0, 0], size: [2, 1]}, {position: [2.5, 0, 0], size: [2, 1]}], 2: [{position: [0, 1, 0], size: [1, 1]}, {position: [1, 1, 0], size: [1, 1]}]}.
                        This is another example: Let's say the sizes the user gave us are 4 meters high and 3 meters wide: {0: [{position: [0, -1, 0], size: [1, 1]}, {position: [1.5, -1, 0], size: [2, 1]}], 1: [{position: [0, 0, 0], size: [1, 1]}, {position: [1, 0, 0], size: [1, 1]}, {position: [2, 0, 0], size: [1, 1]}], 2: [{position: [0, 1, 0], size: [1, 1]}], 3: [{position: [0, 2, 0], size: [1, 1]}]}. This is just an example, be creative!
                        The example above is a valid response because the number of cells in each layer is different and the x-positions of cells are different across layers. In addition, the x-positions and the y-positions of cells are calculated correctly and the size of the cabinet is 3x4 meters.
                        The cabinet must contain at least 2 layers. Be creative but always follow the rules!
                        The calculation for the center of a new cube in x position is as following:
                        Take the x position value of the cube that you are connected to, add the x_length value from the "size" of the cube that you are connected divided by 2 and then add the new cube x_length divided by 2. Your answer should always be in dictionary (python) format, don't add any additional text, just the dictionary."""
        },
        {"role": "user", "content": f"{user_message} , I want you to be unique, don't just give me a boring closet design!"}
    ]

    def is_creative_response(design):
        try:
            layer_count = len(design)
            if layer_count < 2:
                return False

            # Get the number of cells in each layer
            cell_counts = [len(design[layer]) for layer in design]

            # Check if the number of cells in each layer is the same
            if len(set(cell_counts)) == 1:
                # Check x-positions
                for i in range(cell_counts[0]):
                    x_positions = [abs(design[layer][i]['position'][0]) for layer in design if i < len(design[layer])]
                    if len(set(x_positions)) == 1:
                        return False  # Non-creative as x-positions match
            return True  # Design is creative
        except Exception as e:
            print(f"Error in is_creative_response: {e}")
            return False

    def extract_dictionary(response):
        try:
            # Find the JSON-like dictionary in the response using regex
            match = re.search(r"\{[\s\S]*\}", response)
            if not match:
                raise ValueError("Dictionary not found in the response")
            json_str = match.group(0)

            # Replace single quotes with double quotes for JSON compatibility
            json_str = json_str.replace("'", '"')

            # Ensure keys are quoted correctly
            json_str = re.sub(r'(?<=\{|,)\s*(\w+)\s*:', r'"\1":', json_str)

            # Parse the JSON string into a dictionary
            data = json.loads(json_str)
            return data
        except Exception as e:
            print(f"Error: {e}")
            return None

    def correct_x_positions(response):
        try:
            data = extract_dictionary(response)
            if data is None:
                return None
            first_cube_size = 0

            # Iterate through each layer
            for layer_key, cells in data.items():
                # Ensure cells is a list
                if not isinstance(cells, list):
                    continue

                # Iterate through each cell in the layer
                for i in range(len(cells)):
                    # Ensure size is valid
                    x_length = cells[i]['size'][0]
                    if x_length not in [1, 2, 3]:
                        print(f"Invalid x_length!")
                        if x_length < 1:
                            x_length = 1
                        elif x_length < 2:
                            x_length = 1
                        elif x_length < 3:
                            x_length = 2
                        else:
                            x_length = 3
                        cells[i]['size'][0] = x_length

                    if i == 0 and int(layer_key) == 0:
                        # First cell's x position should be 0
                        cells[i]['position'][0] = 0
                        first_cube_size = cells[i]['size'][0]
                    elif i == 0:
                        needed_x = 0 - first_cube_size /2 + (cells[i]['size'][0] / 2)
                        if cells[i]['position'][0] != needed_x:
                            cells[i]['position'][0] = needed_x
                    else:
                        # Calculate the correct x position for the current cell
                        prev_cell = cells[i - 1]
                        prev_x = prev_cell['position'][0]
                        prev_x_length = prev_cell['size'][0]
                        current_x_length = cells[i]['size'][0]

                        expected_x = prev_x + (prev_x_length / 2) + (current_x_length / 2)

                        # Check and correct the x position
                        if cells[i]['position'][0] != expected_x:
                            cells[i]['position'][0] = expected_x

            # Return the modified data
            return data

        except Exception as e:
            print(f"Error: {e}")
            return None

    def handle_offset_adding(cubes: dict):
        collection_of_layer_0 = cubes[0]
        # the last element of the first layer has the largest right edge
        last_element_layer_0 = collection_of_layer_0[-1]
        # according to the largest edge calculate the rest of the cubes offsets in the x-axis
        largest_right_edge = last_element_layer_0['position'][0] + last_element_layer_0['size'][0] / 2
        global_offset = 0.04

        for layer, elements in cubes.items():
            for cube in elements:
                cube_right_edge = cube['position'][0] + cube['size'][0] / 2
                x_offset_value = (largest_right_edge - cube_right_edge) * global_offset
                y_offset_value = int(layer) * global_offset
                # Add the offset attribute
                cube['offset'] = [x_offset_value, y_offset_value]
                cube['display'] = True
        return cubes

    # Send the user message to the ChatGPT model שמג get a response
    chat = client.chat.completions.create(
        model="gpt-4", messages=messages
    )
    reply = chat.choices[0].message.content

    # Extract and clean the response to get only the dictionary
    cleaned_reply = extract_dictionary(reply)

    if cleaned_reply is None:
        return jsonify({"text": "תשובתך לא הייתה בפורמט הנכון, רענן את הדף ונסה שוב בבקשה."})

    # Check if the initial response is creative
    if not is_creative_response(cleaned_reply):
        messages.append({
            "role": "assistant",
            "content": "There was an issue with your response. Please ensure that the design is creative. The number of cells in each layer should not be the same and the x-positions of cells should be different across layers."
        })
        return jsonify({"text": "The response was not creative enough. Please try again."})

    # Correct the x positions
    corrected_reply = correct_x_positions(json.dumps(cleaned_reply))

    if corrected_reply is None:
        return jsonify({"text": "תשובתך לא הייתה בפורמט הנכון, רענן את הדף ונסה שוב בבקשה."})

    messages.append({"role": "assistant", "content": json.dumps(corrected_reply, indent=4)})
    corrected_reply = {int(key): value for key, value in corrected_reply.items()}
    corrected_reply = handle_offset_adding(corrected_reply)
    return jsonify({"text": corrected_reply})

if __name__ == "__main__":
    app.run(debug=True)


#TODO - Check the offset in the upper layers in the closet