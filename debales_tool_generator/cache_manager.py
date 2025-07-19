import json
import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

class CacheManager:
    """Manages multi-layer caching for the Debales Tool Generator."""
    
    def __init__(self, config):
        """Initialize the cache manager.
        
        Args:
            config: DebalesConfig instance with MongoDB connection
        """
        self.collection = config.get_container("cache")
    
    def generate_key(self, prefix: str, data: Any) -> str:
        """Generate a deterministic cache key from the input data.
        
        Args:
            prefix: String prefix for the key
            data: Data to hash for the key
            
        Returns:
            A string key for the cache
        """
        if isinstance(data, dict):
            # Sort dictionary to ensure consistent hashing
            serialized = json.dumps(data, sort_keys=True)
        else:
            serialized = str(data)
            
        # Create hash of the serialized data
        hash_value = hashlib.sha256(serialized.encode()).hexdigest()
        return f"{prefix}:{hash_value}"
    
    def get(self, key: str) -> Optional[Dict]:
        """Get an item from the cache by key.
        
        Args:
            key: The cache key
            
        Returns:
            The cached value or None if not found or expired
        """
        try:
            # Find the item in MongoDB
            item = self.collection.find_one({"_id": key})
            
            if not item:
                return None
                
            # Check if the item has expired
            if "expiry" in item:
                expiry_time = datetime.fromisoformat(item["expiry"])
                if expiry_time < datetime.utcnow():
                    # Item has expired, delete it
                    self.collection.delete_one({"_id": key})
                    return None
            
            # Update last accessed time
            self.collection.update_one(
                {"_id": key},
                {"$set": {"last_accessed": datetime.utcnow().isoformat()}}
            )
            
            return item.get("value")
        except Exception:
            # Item not found or other error
            return None
    
    def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        """Store an item in the cache.
        
        Args:
            key: The cache key
            value: The value to store
            ttl: Time to live in seconds (default: 1 hour)
        """
        # Calculate expiry time
        expiry_time = datetime.utcnow() + timedelta(seconds=ttl)
        
        # Create the cache item
        cache_item = {
            "_id": key,
            "value": value,
            "expiry": expiry_time.isoformat(),
            "last_accessed": datetime.utcnow().isoformat()
        }
        
        # Upsert the item in MongoDB
        self.collection.replace_one({"_id": key}, cache_item, upsert=True)
    
    def delete(self, key: str) -> None:
        """Delete an item from the cache.
        
        Args:
            key: The cache key
        """
        try:
            self.collection.delete_one({"_id": key})
        except Exception:
            # Item not found or other error, ignore
            pass
            
    def clear_expired(self) -> int:
        """Clear all expired items from the cache.
        
        Returns:
            Number of items cleared
        """
        now = datetime.utcnow().isoformat()
        
        # Find and delete all expired items
        result = self.collection.delete_many({"expiry": {"$lt": now}})
        
        return result.deleted_count 