from flask import Flask, jsonify
from werkzeug.utils import secure_filename
from roboflow import Roboflow
import os
import requests
from flask_cors import CORS
import schedule
import time
import threading
import shutil  # Added for file moving

app = Flask(__name__)
CORS(app, support_credentials=True)

# Initialize Roboflow instance
rf = Roboflow(api_key="06AAsOyyx5C7hrsygRQT")
project = rf.workspace().project("binsmaterial")
model = project.version(1).model

# Set the upload folder and allowed extensions
UPLOAD_FOLDER = 'public_html/images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Function to check if the file extension is allowed
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Function to send bin status
import requests

def send_bin_status(bin_no, location, percentage_level, material_type, mobile_no, image_name, token):

    if percentage_level == "overfill":
        percentage_level = "90"
    
    endpoint = "https://rudrayati.in/api/wa/send-bin-status/"
    print(bin_no, location, percentage_level, material_type, mobile_no, image_name, token)

    payload = {
        "bin_no": bin_no,
        "location": location,
        "percentage_level": percentage_level,
        "material_type": material_type,
        "mobile_no": mobile_no,
        "image": image_name,
        "token": token
    }

    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(endpoint, json=payload, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return 500, {"error": f"Request failed: {str(e)}"}

    if response.status_code == 200:
        try:
            response_data = response.json()
        except requests.exceptions.JSONDecodeError:
            response_data = {"error": "Non-JSON response"}
    else:
        response_data = {"error": f"Request failed with status code {response.status_code}"}
    
    print(response.status_code, response_data)
    return response.status_code, response_data

# Scheduler function to hit the API endpoint at 10-minute intervals
def job():
    print("Job started...")

    # Maintain a set to keep track of processed files
    processed_files = set()

    for filename in os.listdir(app.config['UPLOAD_FOLDER']):
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        if not os.path.exists(filepath) or not allowed_file(filename) or filename in processed_files:
            print(f'Skipping file: {filename}')
            continue

        try:
            prediction = model.predict(filepath, confidence=40, overlap=30).json()
        except Exception as e:
            print(f'Error predicting for {filename}: {str(e)}')
            continue

        mobile_no = ""  # Initialize mobile_no outside the loop
        predicted_classes = []
        other_material_types = set()  # Use a set to ensure uniqueness
        percentage_level = ""

        for pred in prediction['predictions']:
            if 'overfill' in pred['class'].lower() or '60-90' in pred['class'].lower():
                mobile_no = "7004933980" if 'overfill' in pred['class'].lower() else "9771302094"
                percentage_level = pred['class']
                predicted_classes.append(pred['class'])
            else:
                other_material_types.add(pred['class'])
                continue

        material_type = ",".join(other_material_types)

        if mobile_no:
            bin_no = "BIN_NO_01"
            location = "001-Pellete-TSJ"
            token = "f591fe9b22b64846c9961da3ff4f0eef9f3e4190ccbc15cfb53e7c24592b7143bccc3e37e0f45d3c1c915b6a0af23953569038cd41a003df9add41ad7c90886c"

            _, response_data = send_bin_status(bin_no=bin_no, location=location, percentage_level=percentage_level, material_type=material_type, mobile_no=mobile_no, image_name=filename, token=token)

            print({'prediction': prediction, 'bin_status_response': response_data})
            processed_files.add(filename)

            # Move the processed file to the 'processed_images' folder
            processed_folder = 'public_html/MovedImages'
            
            # Check if the image has a class of "overfill" or "overflow"
            if any("overfill" in pred['class'].lower() or '60-90' in pred['class'].lower() for pred in prediction['predictions']):
                # Move the processed file to the 'processed_images' folder
                shutil.move(filepath, os.path.join(processed_folder, filename))
            else:
                # Move the file to a different folder for images without the desired class
                no_class_folder = 'public_html/MovedImages'
                os.makedirs(no_class_folder, exist_ok=True)
                shutil.move(filepath, os.path.join(no_class_folder, filename))

    print("Job completed.")


# Schedule the job to run every 10 minutes
schedule.every(10).minutes.do(job)

# Function to run the scheduler in a separate thread
def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    # Start the scheduler in a separate thread
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.start()

    # Start the Flask app
    app.run(debug=True)
