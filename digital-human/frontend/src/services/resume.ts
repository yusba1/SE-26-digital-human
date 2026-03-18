export type UploadResumeResponse = {
  resume_id: string;
  text_length: number;
};

const API_BASE_URL = "http://localhost:8000";

export async function uploadResume(file: File): Promise<UploadResumeResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/api/resume/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    let detail = "上传失败";
    try {
      const errorData = await response.json();
      detail = errorData?.detail || detail;
    } catch {
      // ignore json parse errors
    }
    throw new Error(detail);
  }

  return response.json();
}
