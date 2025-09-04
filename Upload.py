import dash
from dash import dcc, html, Input, Output, State, callback_context
import dash_bootstrap_components as dbc
from datetime import datetime
import base64
import io
import requests
from minio import Minio
from minio.error import S3Error
import os
from urllib.parse import urlparse
import json

# Initialize Dash app with Bootstrap theme

app = dash.Dash(**name**, external_stylesheets=[dbc.themes.BOOTSTRAP])

# MinIO Configuration - Update these with your MinIO settings

MINIO_ENDPOINT = os.getenv(‘MINIO_ENDPOINT’, ‘localhost:9000’)
MINIO_ACCESS_KEY = os.getenv(‘MINIO_ACCESS_KEY’, ‘minioadmin’)
MINIO_SECRET_KEY = os.getenv(‘MINIO_SECRET_KEY’, ‘minioadmin’)
MINIO_BUCKET = os.getenv(‘MINIO_BUCKET’, ‘uploads’)
MINIO_SECURE = os.getenv(‘MINIO_SECURE’, ‘False’).lower() == ‘true’

# Task Service Configuration - Update with your service endpoint

TASK_SERVICE_URL = os.getenv(‘TASK_SERVICE_URL’, ‘http://localhost:8080/api/tasks’)

# Initialize MinIO client

try:
minio_client = Minio(
MINIO_ENDPOINT,
access_key=MINIO_ACCESS_KEY,
secret_key=MINIO_SECRET_KEY,
secure=MINIO_SECURE
)

```
# Create bucket if it doesn't exist
if not minio_client.bucket_exists(MINIO_BUCKET):
    minio_client.make_bucket(MINIO_BUCKET)
    print(f"Bucket '{MINIO_BUCKET}' created successfully")

print(f"Connected to MinIO at {MINIO_ENDPOINT}")
```

except Exception as e:
print(f”Error connecting to MinIO: {e}”)
minio_client = None

# App Layout

app.layout = dbc.Container([
dbc.Row([
dbc.Col([
html.H1(“File Upload & Task Runner”, className=“text-center mb-4”),
html.Hr(),
])
]),

```
# File Upload Section
dbc.Row([
    dbc.Col([
        dbc.Card([
            dbc.CardHeader(html.H4("Upload Files")),
            dbc.CardBody([
                dcc.Upload(
                    id='upload-data',
                    children=html.Div([
                        'Drag and Drop or ',
                        html.A('Select Files')
                    ]),
                    style={
                        'width': '100%',
                        'height': '60px',
                        'lineHeight': '60px',
                        'borderWidth': '1px',
                        'borderStyle': 'dashed',
                        'borderRadius': '5px',
                        'textAlign': 'center',
                        'margin': '10px'
                    },
                    multiple=True
                ),
                html.Div(id='upload-status', className="mt-3")
            ])
        ], className="mb-4")
    ])
]),

# Task Configuration Section
dbc.Row([
    dbc.Col([
        dbc.Card([
            dbc.CardHeader(html.H4("Task Configuration")),
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Task Type:"),
                        dcc.Dropdown(
                            id='task-type',
                            options=[
                                {'label': 'Data Processing', 'value': 'data_processing'},
                                {'label': 'File Analysis', 'value': 'file_analysis'},
                                {'label': 'Model Training', 'value': 'model_training'},
                                {'label': 'Custom Task', 'value': 'custom'}
                            ],
                            value='data_processing',
                            placeholder="Select a task type"
                        )
                    ], width=6),
                    dbc.Col([
                        dbc.Label("Priority:"),
                        dcc.Dropdown(
                            id='task-priority',
                            options=[
                                {'label': 'Low', 'value': 'low'},
                                {'label': 'Medium', 'value': 'medium'},
                                {'label': 'High', 'value': 'high'},
                                {'label': 'Critical', 'value': 'critical'}
                            ],
                            value='medium',
                            placeholder="Select priority"
                        )
                    ], width=6)
                ], className="mb-3"),
                
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Task Parameters (JSON):"),
                        dcc.Textarea(
                            id='task-parameters',
                            placeholder='{"key": "value", "setting": 123}',
                            style={'width': '100%', 'height': 100},
                            value='{"timeout": 300, "retry_count": 3}'
                        )
                    ])
                ], className="mb-3"),
                
                dbc.Row([
                    dbc.Col([
                        dbc.Button(
                            "Run Task",
                            id="run-task-btn",
                            color="primary",
                            size="lg",
                            disabled=True,
                            className="w-100"
                        )
                    ])
                ])
            ])
        ])
    ])
]),

# Results Section
dbc.Row([
    dbc.Col([
        dbc.Card([
            dbc.CardHeader(html.H4("Results")),
            dbc.CardBody([
                html.Div(id='task-results')
            ])
        ], className="mt-4")
    ])
]),

# Store uploaded file paths
dcc.Store(id='uploaded-files', data=[])
```

], fluid=True)

def upload_file_to_minio(file_content, filename):
“”“Upload file to MinIO and return the file path”””
if not minio_client:
return None, “MinIO client not initialized”

```
try:
    # Generate unique filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_filename = f"{timestamp}_{filename}"
    
    # Upload file to MinIO
    file_data = io.BytesIO(file_content)
    minio_client.put_object(
        MINIO_BUCKET,
        unique_filename,
        file_data,
        length=len(file_content)
    )
    
    return unique_filename, None
except S3Error as e:
    return None, f"MinIO error: {e}"
except Exception as e:
    return None, f"Upload error: {e}"
```

def call_task_service(file_paths, task_type, priority, parameters):
“”“Call the task service with uploaded files and configuration”””
try:
# Prepare task payload
task_payload = {
“task_type”: task_type,
“priority”: priority,
“files”: file_paths,
“parameters”: parameters,
“created_at”: datetime.now().isoformat(),
“status”: “pending”
}

```
    # Make API call to task service
    response = requests.post(
        TASK_SERVICE_URL,
        json=task_payload,
        headers={"Content-Type": "application/json"},
        timeout=30
    )
    
    if response.status_code == 200:
        return response.json(), None
    else:
        return None, f"Task service error: {response.status_code} - {response.text}"

except requests.exceptions.RequestException as e:
    return None, f"Request error: {e}"
except Exception as e:
    return None, f"Task service error: {e}"
```

@app.callback(
[Output(‘upload-status’, ‘children’),
Output(‘uploaded-files’, ‘data’),
Output(‘run-task-btn’, ‘disabled’)],
[Input(‘upload-data’, ‘contents’)],
[State(‘upload-data’, ‘filename’),
State(‘uploaded-files’, ‘data’)]
)
def handle_file_upload(contents, filenames, existing_files):
if not contents:
return “”, existing_files, True

```
uploaded_files = existing_files.copy() if existing_files else []
upload_messages = []

# Handle multiple files
if not isinstance(contents, list):
    contents = [contents]
    filenames = [filenames]

for content, filename in zip(contents, filenames):
    # Decode the file content
    content_type, content_string = content.split(',')
    decoded = base64.b64decode(content_string)
    
    # Upload to MinIO
    file_path, error = upload_file_to_minio(decoded, filename)
    
    if error:
        upload_messages.append(
            dbc.Alert(f"Failed to upload {filename}: {error}", color="danger")
        )
    else:
        uploaded_files.append({
            "original_name": filename,
            "minio_path": file_path,
            "size": len(decoded),
            "upload_time": datetime.now().isoformat()
        })
        upload_messages.append(
            dbc.Alert(f"Successfully uploaded {filename} ({len(decoded)} bytes)", color="success")
        )

# Enable run task button if files are uploaded
run_button_disabled = len(uploaded_files) == 0

return upload_messages, uploaded_files, run_button_disabled
```

@app.callback(
Output(‘task-results’, ‘children’),
[Input(‘run-task-btn’, ‘n_clicks’)],
[State(‘uploaded-files’, ‘data’),
State(‘task-type’, ‘value’),
State(‘task-priority’, ‘value’),
State(‘task-parameters’, ‘value’)]
)
def run_task(n_clicks, uploaded_files, task_type, priority, parameters_str):
if not n_clicks or not uploaded_files:
return “”

```
try:
    # Parse parameters JSON
    if parameters_str:
        parameters = json.loads(parameters_str)
    else:
        parameters = {}
except json.JSONDecodeError:
    return dbc.Alert("Invalid JSON in task parameters", color="danger")

# Extract file paths for the task service
file_paths = [file_info["minio_path"] for file_info in uploaded_files]

# Call task service
result, error = call_task_service(file_paths, task_type, priority, parameters)

if error:
    return dbc.Alert(f"Task failed: {error}", color="danger")

# Display success result
result_content = [
    dbc.Alert("Task submitted successfully!", color="success"),
    html.H5("Task Details:"),
    html.P(f"Task ID: {result.get('task_id', 'N/A')}"),
    html.P(f"Type: {task_type}"),
    html.P(f"Priority: {priority}"),
    html.P(f"Files: {len(file_paths)} file(s)"),
    html.P(f"Status: {result.get('status', 'Unknown')}"),
    html.Hr(),
    html.H5("Files Processed:"),
]

# Add file list
file_list = []
for file_info in uploaded_files:
    file_list.append(html.Li(f"{file_info['original_name']} → {file_info['minio_path']}"))

result_content.append(html.Ul(file_list))

# Add raw response if available
if result:
    result_content.extend([
        html.Hr(),
        html.H5("Service Response:"),
        html.Pre(json.dumps(result, indent=2), style={"background": "#f8f9fa", "padding": "10px", "border-radius": "5px"})
    ])

return result_content
```

if **name** == ‘**main**’:
print(“Starting Dash application…”)
print(f”MinIO Endpoint: {MINIO_ENDPOINT}”)
print(f”MinIO Bucket: {MINIO_BUCKET}”)
print(f”Task Service URL: {TASK_SERVICE_URL}”)
print(“Access the application at: http://localhost:8050”)

```
app.run_server(debug=True, host='0.0.0.0', port=8050)
```
