const API_BASE = "/api/v1";

async function fetchSummary() {
    const res = await fetch(`${API_BASE}/dashboard/summary`);
    if (!res.ok) throw new Error(`summary 조회 실패: ${res.status}`);
    return res.json();
}

async function fetchRecords(page = 1, size = 20, characteristic = "") {
    const params = new URLSearchParams({ page, size });
    if (characteristic) params.set("characteristic", characteristic);
    const res = await fetch(`${API_BASE}/dashboard/records?${params}`);
    if (!res.ok) throw new Error(`records 조회 실패: ${res.status}`);
    return res.json();
}

function renderSummary(summary) {
    document.getElementById("total-measurements").textContent =
        summary.total_measurements ?? "-";
    document.getElementById("total-sessions").textContent =
        summary.total_sessions ?? "-";
}

function renderRecords(data) {
    const tbody = document.getElementById("records-body");
    if (!data.items || data.items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8">데이터 없음</td></tr>';
        return;
    }
    tbody.innerHTML = data.items
        .map(
            (r) => `<tr>
            <td>${new Date(r.measured_at).toLocaleString("ko-KR")}</td>
            <td>${r.session_id}</td>
            <td>${r.characteristic}</td>
            <td>${Number(r.value).toExponential(4)}</td>
            <td>${r.unit}</td>
            <td>${r.frequency ?? "-"}</td>
            <td>${r.dc_bias ?? "-"}</td>
            <td>${r.temperature ?? "-"}</td>
        </tr>`
        )
        .join("");
}

async function load() {
    const characteristic = document.getElementById("char-filter").value;
    try {
        const [summary, records] = await Promise.all([
            fetchSummary(),
            fetchRecords(1, 20, characteristic),
        ]);
        renderSummary(summary);
        renderRecords(records);
    } catch (e) {
        console.error("대시보드 로드 실패:", e);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    load();
    document.getElementById("char-filter").addEventListener("change", load);
});
