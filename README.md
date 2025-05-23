# Randata - Your Simple Random Data Generator API

[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/Python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI Version](https://img.shields.io/badge/FastAPI-0.63.0+-blueviolet.svg)](https://fastapi.tiangolo.com/)
[![Uvicorn Version](https://img.shields.io/badge/Uvicorn-0.13.0+-success.svg)](https://www.uvicorn.org/)

**Randata** is a small and straightforward API built with FastAPI that provides various endpoints for generating random data. It's designed to be a simple tool for developers who need quick access to different types of random information without the need for a database.

This project serves as a demonstration of FastAPI capabilities and basic API development skills.

## Features

This API currently offers the following endpoints:

* **`/`**: A simple welcome message.
* **`/random/uuid`**: Generates a random UUID (Universally Unique Identifier).
* **`/random/int`**: Generates a random integer within a specified range (defaults to 0-100).
* **`/random/float`**: Generates a random floating-point number within a specified range (defaults to 0.0-1.0).
* **`/random/string`**: Generates a random string of a specified length (defaults to 16 alphanumeric characters).
* **`/random/secure-password`**: Generates a cryptographically secure random password of a specified length (defaults to 20 characters).
* **`/random/color/hex`**: Generates a random hexadecimal color code.
* **`/random/color/rgb`**: Generates a random RGB color as a JSON object.
* **`/random/date`**: Generates a random date within a specified year range (defaults to 2020-2025).
* **`/random/choice`**: Chooses a random item from a comma-separated list provided as a query parameter.

## Getting Started

To run this API locally, follow these steps:

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/barretobit/Randata.git
    cd Randata
    ```

2.  **Create and activate a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate     # On macOS and Linux
    venv\Scripts\activate        # On Windows (Command Prompt)
    .\venv\Scripts\Activate.ps1  # On Windows (PowerShell)
    ```

3.  **Install the dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *(You'll need to create this file with `pip freeze > requirements.txt` after installing `fastapi` and `uvicorn`)*

4.  **Run the FastAPI application using Uvicorn:**
    ```bash
    uvicorn app.main:app --reload
    ```

5.  **Access the API:**
    Open your web browser or use a tool like `curl` to access the endpoints. The API will be running at `http://127.0.0.1:8000`.

    * **Interactive API Documentation:** You can explore the API's documentation automatically generated by FastAPI at `http://127.0.0.1:8000/docs` or `http://127.0.0.1:8000/redoc`.

## Usage Examples

Here are a few examples of how to use the API:

* **Get a random UUID:**
    ```bash
    curl http://127.0.0.1:8000/random/uuid
    ```
    ```json
    {"uuid": "a1b2c3d4-e5f6-7890-1234-567890abcdef"}
    ```

* **Get a random integer between 1 and 1000:**
    ```bash
    curl http://127.0.0.1:8000/random/int?min=1&max=1000
    ```
    ```json
    {"random_integer": 456}
    ```

* **Get a random secure password of length 25:**
    ```bash
    curl http://127.0.0.1:8000/random/secure-password?length=25
    ```
    ```json
    {"secure_password": "p3!xR9zK*tLmVbSj2hYnCqWfU"}
    ```

* **Get a random choice from a list:**
    ```bash
    curl http://127.0.0.1:8000/random/choice?items=dog,cat,bird,fish
    ```
    ```json
    {"random_choice": "cat"}
    ```

## Deployment

This API is deployed using Render.com:

* **Render:** [randata.onrender.com](https://randata.onrender.com/docs).

It's currently using the free tier Web Service that only have 512 MB RAM and 0.1 CPU. 

## Contributing

Contributions to this project are welcome! If you have ideas for new random data generators or improvements, feel free to open an issue or submit a pull request. 
Once the pull request is approved and merged the new updated version will be deployed into: [randata.onrender.com](https://randata.onrender.com/docs)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


## Author

João Barreto
* **Email:** barretobit@gmx.ch
* **LinkedIn:** [linkedin.com/in/barretobit](linkedin.com/in/barretobit)
* **GitHub:** [github.com/barretobit](github.com/barretobit) 

**Thank you for checking out Randata!**