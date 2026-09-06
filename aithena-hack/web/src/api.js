const API_BASE = "/api";

export async function uploadContracts(files) {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }

  const response = await fetch(`${API_BASE}/ingest`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) throw new Error(`Upload failed: ${response.status}`);
  return response.json();
}

export async function getContracts() {
  const response = await fetch(`${API_BASE}/contracts`);
  if (!response.ok) throw new Error(`Fetch failed: ${response.status}`);
  return response.json();
}

export async function getCalendarEvents() {
  const response = await fetch(`${API_BASE}/calendar`);
  if (!response.ok) throw new Error(`Fetch failed: ${response.status}`);
  return response.json();
}

export async function getConflicts() {
  const response = await fetch(`${API_BASE}/conflicts`);
  if (!response.ok) throw new Error(`Fetch failed: ${response.status}`);
  return response.json();
}