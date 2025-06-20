"""Parser for Ansible Galaxy requirements and metadata."""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

import yaml

from .base import BaseParser

if TYPE_CHECKING:
    from ..commands import Command


class AnsibleGalaxyParser(BaseParser):
    """Parser for Ansible Galaxy requirements and metadata."""

    @property
    def supported_file_patterns(self) -> List[str]:
        """Return supported file patterns for Ansible Galaxy."""
        return [
            "**/requirements.yml",
            "**/requirements.yaml",
            "**/meta/requirements.yml",
            "**/meta/main.yml",
            "**/galaxy.yml",
        ]

    @classmethod
    def can_parse(cls, file_path: Path) -> bool:
        """Check if the file is an Ansible Galaxy requirements or metadata file."""
        if not file_path.exists():
            return False

        # Check for requirements files
        if file_path.name in ["requirements.yml", "requirements.yaml"]:
            return True

        # Check for meta/requirements.yml or meta/main.yml in roles
        if "meta" in file_path.parts and file_path.name in [
            "requirements.yml",
            "main.yml",
        ]:
            return True

        # Check for galaxy.yml for collections
        if file_path.name == "galaxy.yml":
            return True

        return False

    def _parse_requirements_file(
        self, file_path: Path, content: str = None
    ) -> List[Dict[str, Any]]:
        """Parse a requirements.yml file and return a list of requirements.

        Args:
            file_path: Path to the requirements file
            content: Optional content of the file. If not provided, will read from file_path.
        """
        try:
            if content is None:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = yaml.safe_load(f)
            else:
                content = yaml.safe_load(content)

            if not content:
                return []

            # Handle different formats of requirements files
            if isinstance(content, list):
                return content
            elif isinstance(content, dict):
                if "roles" in content:
                    return content.get("roles", [])
                if "collections" in content:
                    return content.get("collections", [])
        except (yaml.YAMLError, UnicodeDecodeError) as e:
            print(f"Error parsing requirements file {file_path}: {e}")

        return []

    def _parse_meta_file(
        self, file_path: Path, content: str = None
    ) -> List[Dict[str, Any]]:
        """Parse a meta/main.yml file and return role dependencies.

        Args:
            file_path: Path to the meta file
            content: Optional content of the file. If not provided, will read from file_path.
        """
        try:
            if content is None:
                with open(file_path, "r", encoding="utf-8") as f:
                    meta = yaml.safe_load(f)
            else:
                meta = yaml.safe_load(content)

            if isinstance(meta, dict) and "dependencies" in meta:
                deps = meta["dependencies"]
                if isinstance(deps, list):
                    return deps
        except (yaml.YAMLError, UnicodeDecodeError) as e:
            print(f"Error parsing meta file {file_path}: {e}")

        return []

    def _parse_galaxy_file(
        self, file_path: Path, content: str = None
    ) -> Dict[str, Any]:
        """Parse a galaxy.yml file and return collection metadata.

        Args:
            file_path: Path to the galaxy.yml file
            content: Optional content of the file. If not provided, will read from file_path.
        """
        try:
            if content is None:
                with open(file_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            else:
                return yaml.safe_load(content) or {}
        except (yaml.YAMLError, UnicodeDecodeError) as e:
            print(f"Error parsing galaxy.yml {file_path}: {e}")
            return {}

    def parse(self, content: str = None) -> "List[Command]":
        """Parse Ansible Galaxy files and extract commands.

        Args:
            content: Optional content of the file. If not provided, will read from file_path.

        Returns:
            List of Command objects
        """
        from domd.core.commands import Command

        if not self.file_path or not self.file_path.exists():
            return []

        self._commands: List[Command] = []

        # Get relative path if file is in project directory, otherwise use full path
        try:
            rel_path = self.file_path.relative_to(self.project_root)
        except ValueError:
            rel_path = self.file_path

        # If content is not provided, read from file
        if content is None and not self.file_path.is_dir():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except (IOError, UnicodeDecodeError):
                # If we can't read the file, return empty list
                return []

        try:
            # Handle requirements files
            if self.file_path.name in ["requirements.yml", "requirements.yaml"]:
                requirements = self._parse_requirements_file(self.file_path, content)
                if requirements:
                    cmd = f"ansible-galaxy install -r {rel_path}"
                    description = f"Install Ansible roles/collections from: {rel_path}"

                    self._commands.append(
                        Command(
                            command=cmd,
                            description=description,
                            type="ansible_galaxy",
                            source=str(self.file_path),
                            metadata={
                                "file_type": "requirements",
                                "requirements": requirements,
                                "file": str(rel_path),
                            },
                        )
                    )

            # Handle meta/main.yml for role dependencies
            elif self.file_path.name == "main.yml" and "meta" in self.file_path.parts:
                deps = self._parse_meta_file(self.file_path, content)
                if deps:
                    cmd = (
                        f"ansible-galaxy install -r {rel_path.parent}/requirements.yml"
                    )
                    description = f"Install role dependencies from: {rel_path}"

                    self._commands.append(
                        Command(
                            command=cmd,
                            description=description,
                            type="ansible_galaxy",
                            source=str(self.file_path),
                            metadata={
                                "file_type": "role_dependencies",
                                "dependencies": deps,
                                "file": str(rel_path),
                            },
                        )
                    )

            # Handle galaxy.yml for collections
            elif self.file_path.name == "galaxy.yml":
                collection_info = self._parse_galaxy_file(self.file_path, content)
                if collection_info:
                    namespace = collection_info.get("namespace", "unknown")
                    name = collection_info.get("name", "unknown")
                    version = collection_info.get("version", "latest")

                    # Build command
                    cmd = f"ansible-galaxy collection build {rel_path.parent}"
                    description = f"Build collection: {namespace}.{name} ({version})"

                    self._commands.append(
                        Command(
                            command=cmd,
                            description=description,
                            type="ansible_galaxy",
                            source=str(self.file_path),
                            metadata={
                                "file_type": "collection_metadata",
                                "namespace": namespace,
                                "name": name,
                                "version": version,
                                "file": str(rel_path),
                            },
                        )
                    )

        except Exception as e:
            print(f"Error processing Ansible Galaxy file {self.file_path}: {e}")

        return self._commands
