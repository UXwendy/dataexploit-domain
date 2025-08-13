"""Organization mapper for handling aliases and hierarchical organization matching."""
import os
import json
from typing import Dict, List, Set, Optional, Tuple
from pathlib import Path


class OrganizationMapper:
    """Maps organization names and aliases to canonical forms."""
    
    def __init__(self, structure_file_path: Optional[str] = None):
        """
        Initialize the organization mapper.
        
        Args:
            structure_file_path: Path to the organizational structure JSON file.
                                If None, will try to find it automatically.
        """
        self.structure_file_path = structure_file_path or self._find_structure_file()
        self.org_data = self._load_structure()
        self._build_mappings()
    
    def _find_structure_file(self) -> Optional[str]:
        """Try to find the organizational structure file."""
        # Try common locations
        possible_paths = [
            "/Users/filipberntsson/Dev/chalmers_graph/chalmers_organizational_structure.json",
            "../chalmers_graph/chalmers_organizational_structure.json",
            "./chalmers_organizational_structure.json"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def _load_structure(self) -> Dict:
        """Load the organizational structure from JSON."""
        if not self.structure_file_path or not os.path.exists(self.structure_file_path):
            # Return empty structure if file not found
            return {}
        
        try:
            with open(self.structure_file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load organizational structure: {e}")
            return {}
    
    def _build_mappings(self):
        """Build various mappings from the organizational structure."""
        # Initialize mappings
        self.name_to_canonical = {}  # Maps any name/alias to canonical name
        self.canonical_to_aliases = {}  # Maps canonical name to all aliases
        self.hierarchy = {}  # Maps child to parent relationships
        self.reverse_hierarchy = {}  # Maps parent to children
        
        # Common abbreviations mapping
        self.abbreviations = {
            "CSE": "Computer Science and Engineering",
            "EE": "Electrical Engineering",
            "ME": "Mechanical Engineering",
            "CE": "Civil Engineering",
            "IE": "Industrial Engineering",
            "MS": "Materials Science",
            "EP": "Engineering Physics",
            "MATH": "Mathematics",
            "PHYS": "Physics",
            "CHEM": "Chemistry",
            "BIO": "Biology",
            "ENV": "Environmental Engineering",
            "ARCH": "Architecture",
            "IT": "Information Technology"
        }
        
        # Add abbreviations to mappings
        for abbr, full_name in self.abbreviations.items():
            self.name_to_canonical[abbr.lower()] = full_name
            self.name_to_canonical[abbr] = full_name
            
            if full_name not in self.canonical_to_aliases:
                self.canonical_to_aliases[full_name] = set()
            self.canonical_to_aliases[full_name].add(abbr)
        
        # Process organizational structure if available
        if self.org_data and 'chalmers_organizational_structure' in self.org_data:
            self._process_structure(self.org_data['chalmers_organizational_structure'])
    
    def _process_structure(self, structure: Dict, parent_name: Optional[str] = None):
        """Recursively process the organizational structure."""
        if 'departments' in structure:
            for dept_key, dept_data in structure['departments'].items():
                dept_name = dept_data.get('name', '')
                
                # Add to mappings
                self._add_to_mappings(dept_name, dept_name)  # Canonical form
                
                # Process sub-departments
                if 'sub_departments' in dept_data:
                    for sub_dept_key, sub_dept_data in dept_data['sub_departments'].items():
                        sub_dept_name = sub_dept_data.get('name', '')
                        
                        # Add to mappings
                        self._add_to_mappings(sub_dept_name, sub_dept_name)
                        
                        # Add hierarchy
                        self.hierarchy[sub_dept_name] = dept_name
                        if dept_name not in self.reverse_hierarchy:
                            self.reverse_hierarchy[dept_name] = set()
                        self.reverse_hierarchy[dept_name].add(sub_dept_name)
                        
                        # Process units
                        if 'units' in sub_dept_data:
                            for unit_key, unit_data in sub_dept_data['units'].items():
                                unit_name = unit_data.get('name', '')
                                
                                # Add to mappings
                                self._add_to_mappings(unit_name, unit_name)
                                
                                # Add hierarchy
                                self.hierarchy[unit_name] = sub_dept_name
                                if sub_dept_name not in self.reverse_hierarchy:
                                    self.reverse_hierarchy[sub_dept_name] = set()
                                self.reverse_hierarchy[sub_dept_name].add(unit_name)
    
    def _add_to_mappings(self, name: str, canonical: str):
        """Add a name and its variations to the mappings."""
        if not name:
            return
        
        # Add exact name
        self.name_to_canonical[name] = canonical
        self.name_to_canonical[name.lower()] = canonical
        
        if canonical not in self.canonical_to_aliases:
            self.canonical_to_aliases[canonical] = set()
        self.canonical_to_aliases[canonical].add(name)
        
        # Add common variations
        # Remove "Department of" prefix
        if name.startswith("Department of "):
            alt_name = name[14:]
            self.name_to_canonical[alt_name] = canonical
            self.name_to_canonical[alt_name.lower()] = canonical
            self.canonical_to_aliases[canonical].add(alt_name)
    
    def map_to_canonical(self, organization: str) -> str:
        """
        Map an organization name to its canonical form.
        
        Args:
            organization: The organization name to map
            
        Returns:
            The canonical organization name
        """
        # Check direct mapping first
        if organization in self.name_to_canonical:
            return self.name_to_canonical[organization]
        
        # Check lowercase
        lower_org = organization.lower()
        if lower_org in self.name_to_canonical:
            return self.name_to_canonical[lower_org]
        
        # Return original if no mapping found
        return organization
    
    def get_search_terms(self, organization: str, include_hierarchy: bool = True) -> List[str]:
        """
        Get all search terms for an organization, including aliases and hierarchy.
        
        Args:
            organization: The organization name
            include_hierarchy: Whether to include parent/child organizations
            
        Returns:
            List of all search terms to use
        """
        # Get canonical name
        canonical = self.map_to_canonical(organization)
        
        # Start with canonical name and all aliases
        search_terms = {canonical}
        if canonical in self.canonical_to_aliases:
            search_terms.update(self.canonical_to_aliases[canonical])
        
        # Add original term if different
        search_terms.add(organization)
        
        if include_hierarchy:
            # Add child organizations
            if canonical in self.reverse_hierarchy:
                for child in self.reverse_hierarchy[canonical]:
                    search_terms.add(child)
                    if child in self.canonical_to_aliases:
                        search_terms.update(self.canonical_to_aliases[child])
        
        return list(search_terms)
    
    def is_child_of(self, child: str, parent: str) -> bool:
        """
        Check if one organization is a child of another.
        
        Args:
            child: The potential child organization
            parent: The potential parent organization
            
        Returns:
            True if child is under parent in hierarchy
        """
        child_canonical = self.map_to_canonical(child)
        parent_canonical = self.map_to_canonical(parent)
        
        # Check direct parent
        if child_canonical in self.hierarchy:
            if self.hierarchy[child_canonical] == parent_canonical:
                return True
            
            # Check grandparent
            direct_parent = self.hierarchy[child_canonical]
            if direct_parent in self.hierarchy:
                return self.hierarchy[direct_parent] == parent_canonical
        
        return False


# Global instance for convenience
_mapper_instance = None


def get_organization_mapper() -> OrganizationMapper:
    """Get or create the global organization mapper instance."""
    global _mapper_instance
    if _mapper_instance is None:
        _mapper_instance = OrganizationMapper()
    return _mapper_instance