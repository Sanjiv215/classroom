const state = { students: [], selectedId: null, currentReportStudentId: null, toastTimer: null };
const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function toast(message, error = false) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.toggle("error", error);
  element.classList.add("show");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => element.classList.remove("show"), 3500);
}

function initials(name) {
  return String(name || "?").trim().split(/\s+/).slice(0, 2).map((part) => part[0] || "").join("").toUpperCase();
}

function scoreClass(average, marksCount = 1) {
  if (!marksCount) return "";
  return average < 60 ? "low" : average < 75 ? "mid" : "";
}

function updateDateHeader() {
  const dateEl = $("#current-date");
  if (dateEl) {
    const today = new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" }).toUpperCase();
    dateEl.textContent = today;
  }
}

function render() {
  const query = $("#search").value.trim().toLowerCase();
  const visible = state.students.filter((s) => `${s.name} ${s.id} ${s.class_name}`.toLowerCase().includes(query));
  $("#nav-count").textContent = state.students.length;
  $("#stat-students").textContent = state.students.length;
  $("#stat-reports").textContent = state.reportCount || 0;

  const scored = state.students.filter((s) => s.marks.length);
  const hasScored = scored.length > 0;
  $("#stat-average").textContent = hasScored ? (scored.reduce((n, s) => n + s.average, 0) / scored.length).toFixed(1) : "—";
  const avgUnit = $("#stat-average-unit");
  if (avgUnit) avgUnit.hidden = !hasScored;

  const hasStudents = state.students.length > 0;
  $("#stat-attendance").textContent = hasStudents ? (state.students.reduce((n, s) => n + Number(s.attendance), 0) / state.students.length).toFixed(1) : "—";
  const attUnit = $("#stat-attendance-unit");
  if (attUnit) attUnit.hidden = !hasStudents;

  $("#student-total").textContent = `Showing ${visible.length} of ${state.students.length} student${state.students.length === 1 ? "" : "s"}`;

  const emptyState = $("#empty-state");
  if (!state.students.length) {
    emptyState.hidden = false;
    emptyState.querySelector("strong").textContent = "Your student list starts here";
    emptyState.querySelector("p").textContent = "Add a student or import marks from a CSV or Excel file.";
    emptyState.querySelector("div:last-child").hidden = false;
  } else if (!visible.length) {
    emptyState.hidden = false;
    emptyState.querySelector("strong").textContent = "No matching students";
    emptyState.querySelector("p").textContent = "Try searching by another student name, ID, or class.";
    emptyState.querySelector("div:last-child").hidden = true;
  } else {
    emptyState.hidden = true;
  }

  $("#student-rows").innerHTML = visible.map((s) => {
    const date = s.updated_at ? new Date(s.updated_at).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "—";
    const avg = s.marks.length ? `${Number(s.average).toFixed(1)}%` : "—";
    const reportText = s.has_report ? "✧ View report" : "✧ Report";
    return `<tr>
      <td><div class="student-cell"><span class="student-avatar">${esc(initials(s.name))}</span><span><span class="student-name">${esc(s.name)}</span><span class="student-id">${esc(s.id)}</span></span></div></td>
      <td>${esc(s.class_name || "—")}</td>
      <td><div class="attendance-wrap"><span>${Number(s.attendance).toFixed(0)}%</span><span class="mini-track"><i style="width:${Math.max(0, Math.min(100, Number(s.attendance)))}%"></i></span></div></td>
      <td><span class="average-pill ${scoreClass(s.average, s.marks.length)}">${avg}</span></td>
      <td>${date}</td>
      <td><div class="row-actions"><button class="row-button" data-action="edit" data-id="${esc(s.id)}">Edit</button><button class="row-button ai" data-action="report" data-id="${esc(s.id)}">${reportText}</button></div></td>
    </tr>`;
  }).join("");
  if (!visible.length) $("#student-rows").innerHTML = "";
}

async function refresh() {
  try {
    const data = await api("/api/students");
    state.students = data.students || [];
    state.reportCount = data.report_count || 0;
    render();
  } catch (error) { toast(error.message, true); }
}

function addMarkRow(mark = {}) {
  const row = document.createElement("div");
  row.className = "mark-row";
  row.innerHTML = `<input aria-label="Subject" data-field="subject" placeholder="e.g. Mathematics" value="${esc(mark.subject || "")}"><input aria-label="Score" data-field="score" type="number" min="0" step="0.1" value="${mark.score ?? ""}" placeholder="0"><input aria-label="Maximum marks" data-field="max_score" type="number" min="0.1" step="0.1" value="${mark.max_score ?? 100}"><button type="button" class="mark-remove" aria-label="Remove subject">×</button>`;
  row.querySelector(".mark-remove").addEventListener("click", () => row.remove());
  $("#mark-fields").append(row);
}

function openStudent(student = null) {
  state.selectedId = student?.id || null;
  const form = $("#student-form");
  form.reset();
  $("#form-error").textContent = "";
  $("#mark-fields").innerHTML = "";
  $("#dialog-title").textContent = student ? "Edit student" : "Add student";
  $("#delete-student").hidden = !student;
  form.elements.id.readOnly = Boolean(student);
  form.elements.id.value = student?.id || "";
  form.elements.name.value = student?.name || "";
  form.elements.class_name.value = student?.class_name || "";
  form.elements.attendance.value = student?.attendance ?? 90;
  form.elements.notes.value = student?.notes || "";
  (student?.marks?.length ? student.marks : [{}]).forEach(addMarkRow);
  $("#student-dialog").showModal();
}

function collectStudent() {
  const form = $("#student-form");
  const marks = [...$("#mark-fields").querySelectorAll(".mark-row")].map((row) => {
    const scoreVal = row.querySelector('[data-field="score"]').value.trim();
    const maxVal = row.querySelector('[data-field="max_score"]').value.trim();
    return {
      subject: row.querySelector('[data-field="subject"]').value.trim(),
      score: scoreVal === "" ? 0 : Number(scoreVal),
      max_score: maxVal === "" ? 100 : Number(maxVal),
    };
  }).filter((mark) => mark.subject);

  const attVal = form.elements.attendance.value.trim();
  const attendance = attVal === "" ? 90 : Number(attVal);

  return {
    id: form.elements.id.value.trim(),
    name: form.elements.name.value.trim(),
    class_name: form.elements.class_name.value.trim(),
    attendance,
    notes: form.elements.notes.value.trim(),
    marks,
  };
}

function reportMarkup(report) {
  const marks = report.marks.map((m) => `<div class="report-subject-row"><span>${esc(m.subject)}</span><span>${Number(m.score).toLocaleString()} / ${Number(m.max_score).toLocaleString()}</span><strong>${(100 * m.score / m.max_score).toFixed(0)}%</strong></div>`).join("");
  return `<div class="report-card"><div class="report-student-header"><div><strong>${esc(report.student_name)}</strong><small>${esc(report.student_id)}${report.class_name ? ` · ${esc(report.class_name)}` : ""}</small></div><span class="grade-badge">${esc(report.grade)}</span></div><div class="report-metrics"><div class="report-metric"><small>Overall average</small><strong>${Number(report.average).toFixed(1)}%</strong></div><div class="report-metric"><small>Attendance</small><strong>${Number(report.attendance).toFixed(1)}%</strong></div><div class="report-metric"><small>Subjects</small><strong>${report.marks.length}</strong></div></div><div class="report-subjects"><h3>SUBJECT PERFORMANCE</h3>${marks}</div><div class="remark-box"><h3>AI-GENERATED EDUCATOR REMARK</h3><p>${esc(report.remark)}</p></div></div>`;
}

function displayReport(report, studentId) {
  state.currentReportStudentId = studentId;
  $("#report-name").textContent = `${report.student_name} · Report card`;
  $("#report-meta").textContent = `${report.class_name || "Student"} · Generated ${new Date(report.created_at).toLocaleString()}`;
  $("#report-content").innerHTML = reportMarkup(report);
  $("#report-dialog").showModal();
}

async function showReport(studentId, forceGenerate = false) {
  const student = state.students.find((s) => s.id === studentId);
  if (!student?.marks?.length) {
    toast("Add at least one subject mark before generating a report.", true);
    openStudent(student);
    return;
  }
  const button = document.querySelector(`[data-action="report"][data-id="${CSS.escape(studentId)}"]`);
  if (button) {
    button.disabled = true;
    button.textContent = forceGenerate ? "Regenerating…" : "Loading…";
  }

  if (student.has_report && !forceGenerate) {
    try {
      const result = await api(`/api/students/${encodeURIComponent(studentId)}/report`);
      displayReport(result.report, studentId);
      return;
    } catch (_err) {
      // Fallback to generating if report not found
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = "✧ View report";
      }
    }
  }

  toast("Generating report remark with Gemini…");
  try {
    const result = await api(`/api/students/${encodeURIComponent(studentId)}/report`, { method: "POST" });
    displayReport(result.report, studentId);
    await refresh();
  } catch (error) {
    toast(error.message, true);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "✧ View report";
    }
  }
}

function selectFile() { $("#file-input").click(); }

$("#new-student").addEventListener("click", () => openStudent());
$("#panel-add").addEventListener("click", () => openStudent());
$("#empty-add").addEventListener("click", () => openStudent());
$("#add-mark").addEventListener("click", () => addMarkRow());
$("#cancel-dialog").addEventListener("click", () => $("#student-dialog").close());
$("#import-button").addEventListener("click", selectFile);
$("#banner-import").addEventListener("click", selectFile);
$("#empty-import").addEventListener("click", selectFile);
$("#search").addEventListener("input", render);

$("#student-rows").addEventListener("click", (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const student = state.students.find((s) => s.id === button.dataset.id);
  if (button.dataset.action === "edit") openStudent(student);
  if (button.dataset.action === "report") showReport(button.dataset.id);
});

$("#student-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#form-error").textContent = "";
  const data = collectStudent();
  try {
    await api("/api/students", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
    $("#student-dialog").close();
    toast(state.selectedId ? "Student record updated." : "Student added.");
    await refresh();
  } catch (error) { $("#form-error").textContent = error.message; }
});

$("#delete-student").addEventListener("click", async () => {
  if (!state.selectedId || !confirm("Delete this student, marks, and generated reports?")) return;
  try {
    await api(`/api/students/${encodeURIComponent(state.selectedId)}`, { method: "DELETE" });
    $("#student-dialog").close();
    toast("Student record deleted.");
    await refresh();
  } catch (error) { $("#form-error").textContent = error.message; }
});

$("#file-input").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const data = new FormData();
  data.append("file", file);
  try {
    const result = await api("/api/import", { method: "POST", body: data });
    toast(`Imported ${result.imported} student${result.imported === 1 ? "" : "s"}.`);
    await refresh();
  } catch (error) { toast(error.message, true); }
  finally { event.target.value = ""; }
});

$("#regenerate-report").addEventListener("click", () => {
  if (state.currentReportStudentId) {
    showReport(state.currentReportStudentId, true);
  }
});

$("#close-report").addEventListener("click", () => $("#report-dialog").close());
$("#close-report-bottom").addEventListener("click", () => $("#report-dialog").close());
$("#print-report").addEventListener("click", () => window.print());
$("#report-dialog").addEventListener("click", (event) => { if (event.target === $("#report-dialog")) $("#report-dialog").close(); });

$("#student-dialog").addEventListener("click", (event) => {
  if (event.target === $("#student-dialog")) $("#student-dialog").close();
});
$("#student-dialog").addEventListener("close", () => {
  state.selectedId = null;
  $("#form-error").textContent = "";
});

document.querySelectorAll(".side-nav .nav-item").forEach((link) => {
  link.addEventListener("click", () => {
    document.querySelectorAll(".side-nav .nav-item").forEach((el) => el.classList.remove("active"));
    link.classList.add("active");
  });
});

updateDateHeader();
refresh();
