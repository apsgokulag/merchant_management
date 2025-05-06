from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
import os
import pandas as pd
from datetime import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import uuid
import json

app = Flask(__name__, 
            template_folder='app/templates')  
app.secret_key = "restaurant_data_management_secret_key"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
DATA_FOLDER = os.path.join(BASE_DIR, 'data')
DOWNLOAD_FOLDER = os.path.join(BASE_DIR, 'downloads')

for folder in [UPLOAD_FOLDER, DATA_FOLDER, DOWNLOAD_FOLDER]:
    os.makedirs(folder, exist_ok=True)

DATA_FILE = os.path.join(DATA_FOLDER, 'restaurant_data.csv')

if not os.path.exists(DATA_FILE):
    columns = [
        'Order Date', 'ONDC Order ID', 'Restaurant Name', 'Restaurant ID', 
        'Locality', 'Order Status', 'Order Total', 'Copay', 'Copay Amount', 
        'Net Bill Value', 'Total Container Charge', 'Total GST', 'Commission %', 
        'GST on commission %', 'TCS', 'TDS', 'GF Platform Fee', 
        'GST on GF Platform Fee', 'Self Delivery Charges', 'Delivery Discount', 
        'Total Payable to Merchant'
    ]
    pd.DataFrame(columns=columns).to_csv(DATA_FILE, index=False)

@app.route('/')
def index():
    return render_template('index.html') 
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.url)
    
    file = request.files['file']
    
    if file.filename == '':
        flash('No file selected')
        return redirect(request.url)
    
    if file:
        try:
            file_path = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(file_path)
            if file.filename.endswith('.csv'):
                df = pd.read_csv(file_path)
            elif file.filename.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file_path)
            else:
                flash('Unsupported file format. Please upload CSV or Excel file.')
                return redirect(request.url)
            required_columns = [
                'Order Date', 'ONDC Order ID', 'Restaurant Name', 'Restaurant ID', 
                'Locality', 'Order Status', 'Order Total', 'Copay', 'Copay Amount', 
                'Net Bill Value', 'Total Container Charge', 'Total GST', 'Commission %', 
                'GST on commission %', 'TCS', 'TDS', 'GF Platform Fee', 
                'GST on GF Platform Fee', 'Self Delivery Charges', 'Delivery Discount', 
                'Total Payable to Merchant'
            ]
            
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                flash(f'Missing columns in the file: {", ".join(missing_columns)}')
                return redirect(request.url)
            try:
                df['Order Date'] = pd.to_datetime(df['Order Date'], errors='coerce', format='mixed')
                if df['Order Date'].isna().any():
                    flash(f'Warning: Some date values could not be parsed. These will be treated as missing.')
                df['Order Date'] = df['Order Date'].dt.strftime('%Y-%m-%d')
                df['Order Date'] = df['Order Date'].fillna('')
                
            except Exception as e:
                flash(f'Warning: Error processing dates: {str(e)}. Continuing with original date format.')
            if os.path.exists(DATA_FILE) and os.path.getsize(DATA_FILE) > 0:
                existing_df = pd.read_csv(DATA_FILE)
                combined_df = pd.concat([existing_df, df], ignore_index=True)
                combined_df = combined_df.drop_duplicates(subset=['ONDC Order ID'], keep='last')
                combined_df.to_csv(DATA_FILE, index=False)
            else:
                df.to_csv(DATA_FILE, index=False)
            
            flash(f'File {file.filename} uploaded and processed successfully!')
        except Exception as e:
            flash(f'Error processing file: {str(e)}')
        if os.path.exists(file_path):
            os.remove(file_path)
    
    return redirect(url_for('index'))

@app.route('/get_data')
def get_data():
    if not os.path.exists(DATA_FILE) or os.path.getsize(DATA_FILE) == 0:
        return jsonify({'data': []})
    
    df = pd.read_csv(DATA_FILE)
    return jsonify({'data': df.to_dict('records')})

@app.route('/get_restaurants')
def get_restaurants():
    if not os.path.exists(DATA_FILE) or os.path.getsize(DATA_FILE) == 0:
        return jsonify({'restaurants': []})
    
    df = pd.read_csv(DATA_FILE)
    restaurants = df['Restaurant Name'].unique().tolist()
    return jsonify({'restaurants': restaurants})

@app.route('/download', methods=['POST'])
def download_data():
    data = request.json
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    restaurant = data.get('restaurant')
    
    if not os.path.exists(DATA_FILE) or os.path.getsize(DATA_FILE) == 0:
        return jsonify({'error': 'No data available to download'}), 400
    
    try:
        df = pd.read_csv(DATA_FILE)
        
        try:
            df['Order Date'] = pd.to_datetime(df['Order Date'], errors='coerce', format='mixed')
        except Exception as e:
            return jsonify({'error': f'Error processing dates: {str(e)}'}), 500
        if start_date and end_date:
            try:
                start_date = pd.to_datetime(start_date)
                end_date = pd.to_datetime(end_date)
                df = df[(df['Order Date'] >= start_date) & (df['Order Date'] <= end_date)]
            except Exception as e:
                return jsonify({'error': f'Error filtering by date: {str(e)}'}), 500
        
        if restaurant and restaurant != 'All':
            df = df[df['Restaurant Name'] == restaurant]
        
        df['Order Date'] = df['Order Date'].dt.strftime('%Y-%m-%d')
        
        if df.empty:
            return jsonify({'error': 'No data matches the selected filters'}), 400
        
        filename = f"restaurant_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        download_path = os.path.join(DOWNLOAD_FOLDER, filename)
        df.to_excel(download_path, index=False)
        return jsonify({'filename': filename}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_download/<filename>')
def get_download(filename):
    try:
        download_path = os.path.join(DOWNLOAD_FOLDER, filename)
        return send_file(download_path, as_attachment=True)
    except Exception as e:
        flash(f'Error downloading file: {str(e)}')
        return redirect(url_for('index'))

@app.route('/delete_data', methods=['POST'])
def delete_data():
    data = request.json
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    restaurant = data.get('restaurant')
    
    if not os.path.exists(DATA_FILE) or os.path.getsize(DATA_FILE) == 0:
        return jsonify({'error': 'No data available to delete'}), 400
    
    try:
        df = pd.read_csv(DATA_FILE)
        original_count = len(df)
        try:
            df['Order Date'] = pd.to_datetime(df['Order Date'], errors='coerce', format='mixed')
        except Exception as e:
            return jsonify({'error': f'Error processing dates: {str(e)}'}), 500
        keep_mask = pd.Series(True, index=df.index)
        if start_date and end_date:
            try:
                start_date = pd.to_datetime(start_date)
                end_date = pd.to_datetime(end_date)
                date_mask = (df['Order Date'] >= start_date) & (df['Order Date'] <= end_date)
                keep_mask = keep_mask & (~date_mask)
            except Exception as e:
                return jsonify({'error': f'Error filtering by date: {str(e)}'}), 500
        
        if restaurant and restaurant != 'All':
            restaurant_mask = df['Restaurant Name'] == restaurant
            keep_mask = keep_mask & (~restaurant_mask)
        df_filtered = df[keep_mask]
        df_filtered['Order Date'] = df_filtered['Order Date'].dt.strftime('%Y-%m-%d')
        df_filtered.to_csv(DATA_FILE, index=False)
        records_deleted = original_count - len(df_filtered)
        return jsonify({
            'success': True,
            'message': f'{records_deleted} records deleted successfully'
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/send_email', methods=['POST'])
def send_email():
    data = request.json
    recipient_email = data.get('email')
    date = data.get('date')
    
    if not recipient_email:
        return jsonify({'error': 'Email address is required'}), 400
    
    if not date:
        return jsonify({'error': 'Date is required'}), 400
    
    try:
        if not os.path.exists(DATA_FILE) or os.path.getsize(DATA_FILE) == 0:
            return jsonify({'error': 'No data available to generate summary'}), 400
        
        df = pd.read_csv(DATA_FILE)
        try:
            df['Order Date'] = pd.to_datetime(df['Order Date'], errors='coerce', format='mixed')
        except Exception as e:
            return jsonify({'error': f'Error processing dates: {str(e)}'}), 500
        try:
            date_obj = pd.to_datetime(date)
            df_date = df[df['Order Date'].dt.date == date_obj.date()]
        except Exception as e:
            return jsonify({'error': f'Error filtering by date: {str(e)}'}), 500
        
        if df_date.empty:
            return jsonify({'error': f'No data available for {date}'}), 400
        summary = {
            'date': date,
            'total_orders': len(df_date),
            'total_value': df_date['Order Total'].sum(),
            'restaurants': df_date['Restaurant Name'].nunique(),
            'completed_orders': len(df_date[df_date['Order Status'] == 'Completed']),
            'cancelled_orders': len(df_date[df_date['Order Status'] == 'Cancelled']),
            'total_payable_to_merchants': df_date['Total Payable to Merchant'].sum()
        }
        
        summary_filename = f"summary_{date.replace('-', '')}.xlsx"
        summary_path = os.path.join(DOWNLOAD_FOLDER, summary_filename)
        
        df_date['Order Date'] = df_date['Order Date'].dt.strftime('%Y-%m-%d')
        df_date.to_excel(summary_path, index=False)
        
        try:
            sender_email = "your_email@example.com"
            sender_password = "your_password"
            
            msg = MIMEMultipart()
            msg['From'] = sender_email
            msg['To'] = recipient_email
            msg['Subject'] = f"Restaurant Order Summary for {date}"
            
            body = f"""
            <html>
            <body>
                <h2>Restaurant Order Summary for {date}</h2>
                <p>Please find below the summary of orders for {date}:</p>
                <ul>
                    <li>Total Orders: {summary['total_orders']}</li>
                    <li>Total Order Value: {summary['total_value']:.2f}</li>
                    <li>Number of Restaurants: {summary['restaurants']}</li>
                    <li>Completed Orders: {summary['completed_orders']}</li>
                    <li>Cancelled Orders: {summary['cancelled_orders']}</li>
                    <li>Total Payable to Merchants: {summary['total_payable_to_merchants']:.2f}</li>
                </ul>
                <p>Detailed information is attached in the Excel file.</p>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(body, 'html'))
            
            with open(summary_path, 'rb') as file:
                attachment = MIMEApplication(file.read(), _subtype='xlsx')
                attachment.add_header('Content-Disposition', 'attachment', filename=summary_filename)
                msg.attach(attachment)
            
            """
            server = smtplib.SMTP('smtp.example.com', 587)
            server.starttls()
            server.login(sender_email, sender_password)
            text = msg.as_string()
            server.sendmail(sender_email, recipient_email, text)
            server.quit()
            """
            
            return jsonify({
                'success': True,
                'message': f'Email would be sent to {recipient_email} with summary for {date}. (Note: Actual email sending is disabled in this demo)'
            }), 200
            
        except Exception as e:
            return jsonify({'error': f'Email error: {str(e)}'}), 500
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)