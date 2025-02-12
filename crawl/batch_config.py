import os
import json
from utils.common import setup_logger


class BatchConfig:
    """Manage batch download configuration settings"""

    def __init__(self, config_file="batch_config.json"):
        self.config_file = config_file
        self.logger = setup_logger()
        self.load_defaults()
        # Try to load existing settings, fall back to defaults if failed
        if not self.load():
            self.save()  # Save defaults if no config exists

    def load_defaults(self):
        """Set default configuration values"""
        self.settings = {
            "download": {
                "chunk_size": 50,
                "max_workers": 4,
                "batch_size": 5,
                "max_tabs": 3,
                "retry_mode": False,
                "timeout": 30,
                "max_retries": 3,
            },
            "paths": {
                "download_dir": "downloads",
                "batch_dir": "batches",
                "log_dir": "logs",
            },
            "network": {
                "concurrent_downloads": 8,
                "delay_between_batches": 0.2,
                "connection_timeout": 5,
            },
        }

    def load(self):
        """Load configuration from file with backup handling"""
        try:
            if os.path.exists(self.config_file):
                # Make backup before loading
                backup_file = f"{self.config_file}.bak"
                try:
                    import shutil

                    shutil.copy2(self.config_file, backup_file)
                except Exception as e:
                    self.logger.warning(f"Failed to create backup: {e}")

                with open(self.config_file, "r") as f:
                    saved = json.load(f)
                    # Validate and merge with defaults
                    for section in self.settings:
                        if section in saved and isinstance(saved[section], dict):
                            # Only update known settings
                            valid_updates = {
                                k: v
                                for k, v in saved[section].items()
                                if k in self.settings[section]
                            }
                            self.settings[section].update(valid_updates)
                return True

        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in config file: {e}")
            # Try to restore from backup
            self._restore_from_backup()
        except Exception as e:
            self.logger.error(f"Error loading config: {e}")
        return False

    def save(self):
        """Save configuration with atomic write"""
        temp_file = f"{self.config_file}.tmp"
        try:
            # Write to temporary file first
            with open(temp_file, "w") as f:
                json.dump(self.settings, f, indent=4)

            # Atomic replace
            if os.path.exists(self.config_file):
                os.replace(temp_file, self.config_file)
            else:
                os.rename(temp_file, self.config_file)

            self.logger.debug("Settings saved successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error saving config: {e}")
            if os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except OSError:
                    pass
            return False

    def _restore_from_backup(self):
        """Try to restore config from backup file"""
        backup_file = f"{self.config_file}.bak"
        try:
            if os.path.exists(backup_file):
                import shutil

                shutil.copy2(backup_file, self.config_file)
                self.logger.info("Restored config from backup")
                return self.load()
        except Exception as e:
            self.logger.error(f"Failed to restore from backup: {e}")
        return False

    def configure_interactive(self):
        """Interactive configuration setup"""
        print("\nBatch Download Configuration")
        print("==========================")

        sections = {
            "1": ("Download Settings", "download"),
            "2": ("Path Settings", "paths"),
            "3": ("Network Settings", "network"),
        }

        while True:
            print("\nConfiguration Sections:")
            for key, (name, _) in sections.items():
                print(f"{key}. {name}")
            print("4. Save and Exit")
            print("5. Reset to Defaults")

            choice = input("\nSelect section (1-5): ").strip()

            if choice == "4":
                self.save()
                break
            elif choice == "5":
                self.load_defaults()
                print("Settings reset to defaults")
                continue
            elif choice in sections:
                self._configure_section(sections[choice][1])

    def _configure_section(self, section):
        """Configure a specific settings section"""
        print(f"\nConfigure {section}:")
        settings = self.settings[section]

        for key, value in settings.items():
            while True:
                print(f"\nCurrent {key}: {value}")
                new_value = input(
                    "Enter new value (or press Enter to keep current): "
                ).strip()

                if not new_value:
                    break

                try:
                    # Convert value to same type as current setting
                    if isinstance(value, bool):
                        new_value = new_value.lower() in ("true", "yes", "1", "y")
                    else:
                        new_value = type(value)(new_value)

                    # Validate ranges for specific settings
                    if key == "max_workers":
                        new_value = max(1, min(16, new_value))
                    elif key == "batch_size":
                        new_value = max(1, min(100, new_value))
                    elif key == "chunk_size":
                        new_value = max(10, min(500, new_value))

                    settings[key] = new_value
                    break
                except ValueError:
                    print("Invalid value. Please try again.")

    def get_settings(self):
        """Get current settings"""
        return self.settings
