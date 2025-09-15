from .celery_app import celery_app
from .modules.video_decoder import split_video_by_gpu

@celery_app.task
def decode_video(video_path: str, output_dir: str, num_splits: int = 4):
    """
    Celery task to split a video into multiple parts using GPU acceleration.
    """
    print(f"[Task Received] Decode video: {video_path}")
    print(f"Output directory: {output_dir}")
    print(f"Number of splits: {num_splits}")

    try:
        # Call the actual video splitting function
        successful_splits = split_video_by_gpu(
            video_path=video_path,
            output_dir=output_dir,
            num_splits=num_splits
        )

        if successful_splits and len(successful_splits) == num_splits:
            result_message = f"Successfully split video into {len(successful_splits)} parts in {output_dir}"
            print(result_message)
            return {"status": "success", "files": successful_splits, "message": result_message}
        else:
            error_message = f"Failed to split video. Only {len(successful_splits)} parts were created."
            print(error_message)
            return {"status": "failure", "files": successful_splits, "message": error_message}

    except Exception as e:
        error_message = f"An exception occurred during video splitting: {e}"
        print(error_message)
        # It's good practice to reraise the exception if you want the task to be marked as FAILED
        # raise e
        return {"status": "error", "message": error_message}
