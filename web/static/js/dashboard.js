const API_BASE = "/api/v1";

async function fetchSummary() {
    const res = await fetch(`${API_BASE}/dashboard/summary`);
    return res.json();
}

async function fetchRecords(page = 1, size = 20) {
    const res = await fetch(`${API_BASE}/dashboard/records?page=${page}&size=${size}`);
    return res.json();
}

async function init() {
    const summary = await fetchSummary();
    const records = await fetchRecords();
    console.log("summary:", summary);
    console.log("records:", records);
    // TODO: DOM 렌더링 구현
}

document.addEventListener("DOMContentLoaded", init);
