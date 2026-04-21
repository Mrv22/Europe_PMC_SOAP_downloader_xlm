# Europe PMC SOAP Downloader

This repository contains a script that interacts with the Europe PMC SOAP API to download and process scientific data in XML format.

## Installation

To install the necessary packages, run:

```bash
pip install requests xml.etree.ElementTree
```

## Usage

To use the script, execute the following command:

```bash
python downloader.py
```

Ensure you have your API token from Europe PMC, which you can set in the `config.py` file.

## Configuration

Edit the `config.py` file to include your user credentials and desired parameters for the download.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.