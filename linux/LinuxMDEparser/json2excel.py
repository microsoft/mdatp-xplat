#!/usr/bin/env python3
"""Convert MDE JSON logs to CSV format.

This module provides functionality to convert Microsoft Defender for Endpoint
JSON log files to CSV format for easier analysis.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class ConversionError(Exception):
    """Exception raised for JSON to CSV conversion errors."""

    pass


class Json2Excel:
    """Convert JSON log files to CSV format.

    Attributes:
        logfile: Path to the input JSON file.
        filename: Path to the output CSV file.
    """

    def __init__(self, logfile: str | Path, filename: str | Path) -> None:
        """Initialize the converter.

        Args:
            logfile: Path to the input JSON file.
            filename: Path to the output CSV file.
        """
        self.logfile = Path(logfile)
        self.filename = Path(filename)

    def convert(self) -> bool:
        """Convert the JSON log file to CSV format.

        Returns:
            True if conversion was successful, False otherwise.

        Raises:
            ConversionError: If the conversion fails.
        """
        try:
            with open(self.logfile, encoding="utf-8") as json_file:
                log_dict: dict[str, Any] = json.load(json_file)

            if not log_dict:
                logger.warning("JSON file is empty: %s", self.logfile)
                return False

            # Get the first key in the dictionary
            dict_key = next(iter(log_dict))
            data = log_dict[dict_key]

            if not data or not isinstance(data, list):
                logger.warning("No data found in JSON file under key '%s'", dict_key)
                return False

            keys = data[0].keys()

            with open(self.filename, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=keys)
                writer.writeheader()
                writer.writerows(data)

            logger.info("Successfully created %s", self.filename)
            return True

        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON file %s: %s", self.logfile, e)
            raise ConversionError(f"Invalid JSON in {self.logfile}") from e
        except FileNotFoundError as e:
            logger.error("File not found: %s", self.logfile)
            raise ConversionError(f"File not found: {self.logfile}") from e
        except (KeyError, IndexError) as e:
            logger.error("Unexpected JSON structure in %s: %s", self.logfile, e)
            raise ConversionError(f"Unexpected JSON structure: {e}") from e
        except OSError as e:
            logger.error("I/O error: %s", e)
            raise ConversionError(f"I/O error: {e}") from e

    # Alias for backward compatibility
    def json2excel(self) -> bool:
        """Alias for convert() for backward compatibility.

        Returns:
            True if conversion was successful, False otherwise.
        """
        return self.convert()
