from abc import ABC, abstractmethod
import shutil
import os
from fastapi import UploadFile
from app.core.config import settings
import uuid

class FileService(ABC):
    @abstractmethod
    async def save_file(self, file: UploadFile) -> str:
        """Save file and return the path/url"""
        pass

    @abstractmethod
    async def delete_file(self, file_path: str) -> bool:
        """Delete file"""
        pass

class LocalFileService(FileService):
    def __init__(self):
        self.upload_dir = settings.UPLOAD_DIR
        os.makedirs(self.upload_dir, exist_ok=True)

    async def save_file(self, file: UploadFile) -> str:
        # Generate unique filename to avoid collisions
        file_ext = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = os.path.join(self.upload_dir, unique_filename)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        return file_path

    async def delete_file(self, file_path: str) -> bool:
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False
