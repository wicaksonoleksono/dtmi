"""
Metadata processing service for async loading of images, CSV, and references
"""

import asyncio
import uuid
import time
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from ..model.chat_models import (
    MetadataLoadingTask, MetadataResponse,
    ProcessedCSV
)
from ..model.ref_models import ProcessedImage, Reference
from ..utils import process_images, process_csv_files, extract_references
from ..decorators import handle_service_errors, ok, bad


class MetadataService:
    """Service for handling metadata processing asynchronously with smart cleanup"""

    def __init__(self):
        self.task_storage: Dict[str, MetadataLoadingTask] = {}
        self.result_storage: Dict[str, MetadataResponse] = {}
        self.thread_pool = ThreadPoolExecutor(max_workers=4)  # Reduced workers
        
        # Smart cleanup settings
        self.max_memory_mb = 20  # Per-instance memory limit
        self.auto_cleanup_seconds = 30  # Auto-cleanup after 30 seconds
        self.cleanup_tasks: Dict[str, asyncio.Task] = {}
        self.current_memory_usage = 0

    def prepare_metadata_from_rag(
        self,
        rag_result: Dict[str, Any]
    ) -> Optional[MetadataLoadingTask]:
        """
        Prepare metadata task from RAG result
        Single responsibility: metadata preparation and task creation
        """
        csv_paths = rag_result.get('csv_paths', [])
        image_paths = rag_result.get('image_paths', [])
        metadatas = rag_result.get('metadatas', [])

        # Only create task if there's actually metadata to process
        if not csv_paths and not image_paths and not metadatas:
            return None

        return self.create_metadata_task(csv_paths, image_paths, metadatas)

    def start_metadata_task_async(
        self,
        rag_result: Dict[str, Any]
    ) -> Optional[str]:
        """
        Create metadata task and start processing in background (NON-BLOCKING)
        Returns task_id immediately for client polling
        """
        task = self.prepare_metadata_from_rag(rag_result)
        if not task:
            return None

        # Start processing in background (non-blocking)
        asyncio.create_task(self.process_metadata_async(task.task_id))

        ok(f"Started background metadata task: {task.task_id}")
        return task.task_id

    def create_metadata_task(
        self,
        csv_paths: List[str] = None,
        image_paths: List[str] = None,
        metadatas: List[Dict[str, Any]] = None
    ) -> MetadataLoadingTask:
        """Create a metadata loading task"""
        task_id = str(uuid.uuid4())
        task = MetadataLoadingTask(
            csv_paths=csv_paths or [],
            image_paths=image_paths or [],
            metadatas=metadatas or [],
            task_id=task_id,
            status="pending"
        )

        self.task_storage[task_id] = task
        ok(f"Created metadata task: {task_id}")
        return task

    @handle_service_errors(service_name="MetadataService")
    async def process_metadata_async(self, task_id: str) -> MetadataResponse:
        """Process metadata asynchronously"""
        if task_id not in self.task_storage:
            raise ValueError(f"Task {task_id} not found")

        task = self.task_storage[task_id]
        task.status = "processing"

        start_time = time.time()
        ok(f"Starting async metadata processing for task: {task_id}")

        try:
            # Process in parallel using asyncio
            csv_task = self._process_csv_async(task.csv_paths)
            image_task = self._process_images_async(task.image_paths)
            ref_task = self._process_references_async(task.metadatas)
            csv_tables, processed_images, references = await asyncio.gather(
                csv_task, image_task, ref_task, return_exceptions=True
            )
            if isinstance(csv_tables, Exception):
                bad(f"CSV processing failed: {csv_tables}")
                csv_tables = []
            if isinstance(processed_images, Exception):
                bad(f"Image processing failed: {processed_images}")
                processed_images = []
            if isinstance(references, Exception):
                bad(f"Reference processing failed: {references}")
                references = []
            processing_time = time.time() - start_time
            response = MetadataResponse(
                csv_tables=csv_tables,
                processed_images=processed_images,
                references=references,
                task_id=task_id,
                status="completed",
                processing_time=processing_time
            )
            self.result_storage[task_id] = response
            task.status = "completed"
            
            # Track memory usage and start auto-cleanup timer
            self._update_memory_usage(response)
            self._schedule_auto_cleanup(task_id)
            
            ok(f"Completed metadata processing for task {task_id} in {processing_time:.2f}s")
            return response
        except Exception as e:
            task.status = "error"
            bad(f"Error processing metadata task {task_id}: {e}")
            raise

    async def _process_csv_async(self, csv_paths: List[str]) -> List[ProcessedCSV]:
        """Process CSV files asynchronously"""
        if not csv_paths:
            return []

        loop = asyncio.get_event_loop()

        # Convert csv_paths to tuples if they're not already
        csv_tuples = []
        for path in csv_paths:
            if isinstance(path, (list, tuple)) and len(path) >= 2:
                csv_tuples.append((path[0], path[1]))
            elif isinstance(path, str):
                csv_tuples.append((path, ""))
            else:
                csv_tuples.append((str(path), ""))

        # Process in thread pool
        processed_csvs = await loop.run_in_executor(
            self.thread_pool,
            process_csv_files,
            csv_tuples
        )

        # Convert to dataclasses
        csv_tables = []
        for csv_data in processed_csvs:
            try:
                csv_table = ProcessedCSV(**csv_data)
                csv_tables.append(csv_table)
            except Exception as e:
                bad(f"Error creating ProcessedCSV: {e}")
                # Create error CSV
                error_csv = ProcessedCSV(
                    filename="Error",
                    caption="Failed to process CSV",
                    headers=["Error"],
                    rows=[["Processing failed"]],
                    error=True,
                    error_message=str(e)
                )
                csv_tables.append(error_csv)

        ok(f"Processed {len(csv_tables)} CSV files")
        return csv_tables

    async def _process_images_async(self, image_paths: List[str]) -> List[ProcessedImage]:
        """Process images asynchronously"""
        if not image_paths:
            return []

        loop = asyncio.get_event_loop()

        # Convert image_paths to tuples if needed
        image_tuples = []
        for path in image_paths:
            if isinstance(path, (list, tuple)) and len(path) >= 2:
                image_tuples.append((path[0], path[1]))
            elif isinstance(path, str):
                image_tuples.append((path, ""))
            else:
                image_tuples.append((str(path), ""))

        # Process in thread pool
        processed_imgs = await loop.run_in_executor(
            self.thread_pool,
            process_images,
            image_tuples
        )

        # Convert to dataclasses
        processed_images = []
        for img_data in processed_imgs:
            try:
                processed_image = ProcessedImage(**img_data)
                processed_images.append(processed_image)
            except Exception as e:
                bad(f"Error creating ProcessedImage: {e}")
                # Create error image
                error_img = ProcessedImage(
                    path="",
                    filename="Error",
                    caption="Failed to process image",
                    error=True,
                    error_message=str(e)
                )
                processed_images.append(error_img)

        ok(f"Processed {len(processed_images)} images")
        return processed_images

    async def _process_references_async(self, metadatas: List[Dict[str, Any]]) -> List[Reference]:
        """Process references asynchronously"""
        if not metadatas:
            return []

        loop = asyncio.get_event_loop()

        # Process in thread pool
        ref_data = await loop.run_in_executor(
            self.thread_pool,
            extract_references,
            metadatas
        )

        # Convert to dataclasses
        references = []
        for ref in ref_data:
            try:
                reference = Reference(**ref)
                references.append(reference)
            except Exception as e:
                bad(f"Error creating Reference: {e}")

        ok(f"Processed {len(references)} references")
        return references

    def get_task_status(self, task_id: str) -> Optional[str]:
        """Get status of a metadata task"""
        if task_id in self.task_storage:
            return self.task_storage[task_id].status
        return None

    def get_result(self, task_id: str) -> Optional[MetadataResponse]:
        """Get result of completed metadata task"""
        return self.result_storage.get(task_id)

    def cleanup_task(self, task_id: str):
        """Clean up completed task with memory release"""
        # Cancel auto-cleanup timer if exists
        if task_id in self.cleanup_tasks:
            self.cleanup_tasks[task_id].cancel()
            del self.cleanup_tasks[task_id]
        
        # Release memory from result before deletion
        if task_id in self.result_storage:
            result = self.result_storage[task_id]
            self._release_memory(result)
        
        self.task_storage.pop(task_id, None)
        self.result_storage.pop(task_id, None)
        ok(f"Cleaned up task: {task_id}")

    def _schedule_auto_cleanup(self, task_id: str):
        """Schedule automatic cleanup for a task"""
        async def auto_cleanup():
            await asyncio.sleep(self.auto_cleanup_seconds)
            if task_id in self.result_storage:
                self.cleanup_task(task_id)
                ok(f"Auto-cleaned up task: {task_id}")
        
        cleanup_task = asyncio.create_task(auto_cleanup())
        self.cleanup_tasks[task_id] = cleanup_task

    def _update_memory_usage(self, response: MetadataResponse):
        """Estimate and track memory usage"""
        estimated_size = 0
        
        # Estimate image memory (base64 data)
        for img in response.processed_images:
            if hasattr(img, 'data') and img.data:
                # Base64 is ~1.33x the original size
                estimated_size += len(img.data) * 0.75  # Rough estimate
        
        self.current_memory_usage += estimated_size
        
        # Force cleanup if memory limit exceeded
        if self.current_memory_usage > self.max_memory_mb * 1024 * 1024:
            self._force_cleanup_oldest()

    def _release_memory(self, response: MetadataResponse):
        """Release memory from a response object"""
        memory_released = 0
        
        # Clear image base64 data
        for img in response.processed_images:
            if hasattr(img, 'data') and img.data:
                memory_released += len(img.data) * 0.75
                img.data = None  # Release base64 memory
        
        self.current_memory_usage = max(0, self.current_memory_usage - memory_released)

    def _force_cleanup_oldest(self):
        """Force cleanup of oldest tasks when memory limit exceeded"""
        if not self.result_storage:
            return
            
        # Get oldest task (assuming task_id includes timestamp)
        oldest_task_id = min(self.result_storage.keys())
        self.cleanup_task(oldest_task_id)
        ok(f"Force cleaned up oldest task: {oldest_task_id}")

    def get_service_info(self) -> Dict[str, Any]:
        """Get service information"""
        return {
            "service_type": "MetadataService",
            "active_tasks": len(self.task_storage),
            "completed_results": len(self.result_storage),
            "thread_pool_workers": self.thread_pool._max_workers,
            "memory_usage_mb": round(self.current_memory_usage / (1024 * 1024), 2),
            "memory_limit_mb": self.max_memory_mb,
            "auto_cleanup_tasks": len(self.cleanup_tasks)
        }
