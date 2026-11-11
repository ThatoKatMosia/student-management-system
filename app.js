const form = document.querySelector("#student-form");
const studentDialog = document.querySelector("#student-dialog");
const detailDialog = document.querySelector("#detail-dialog");
const searchInput = document.querySelector("#search-input");
const rows = document.querySelector("#student-rows");
const emptyState = document.querySelector("#empty-state");
const dialogError = document.querySelector("#dialog-error");
let students = [];
let editingId = null;
let toastTimeout;

const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[character]));

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Something went wrong. Please try again.");
  return result;
}

function initials(student) {
  return `${student.first_name.trim().charAt(0)}${student.last_name.trim().charAt(0)}`.toUpperCase();
}

function statusClass(status) {
  return `status-${status.toLowerCase().replace(/\s+/g, "-")}`;
}

function updateSummary() {
  document.querySelector("#total-count").textContent = students.length;
  document.querySelector("#active-count").textContent = students.filter((student) => student.status === "Active").length;
  document.querySelector("#leave-count").textContent = students.filter((student) => student.status === "On leave").length;
  document.querySelector("#graduated-count").textContent = students.filter((student) => student.status === "Graduated").length;
  document.querySelector("#nav-count").textContent = students.length;
  document.querySelector("#result-count").textContent = students.length;
}

function renderStudents() {
  updateSummary();
  rows.replaceChildren();
  const query = searchInput.value.trim().toLowerCase();
  const filtered = students.filter((student) =>
    [student.student_id, student.first_name, student.last_name, student.email, student.course, student.status]
      .some((value) => value.toLowerCase().includes(query)));

  filtered.forEach((student, index) => {
    const row = document.createElement("tr");
    const tone = index % 5;
    row.innerHTML = `
      <td><div class="student-cell">
        <span class="student-avatar ${tone ? `tone-${tone}` : ""}">${escapeHtml(initials(student))}</span>
        <span><span class="student-name">${escapeHtml(student.first_name)} ${escapeHtml(student.last_name)}</span>
        <span class="student-email">${escapeHtml(student.email)}</span></span>
      </div></td>
      <td><span class="student-id">${escapeHtml(student.student_id)}</span></td>
      <td><span class="course-name">${escapeHtml(student.course)}</span></td>
      <td>Year ${escapeHtml(student.year)}</td>
      <td><span class="status-pill ${statusClass(student.status)}">${escapeHtml(student.status)}</span></td>
      <td><div class="row-actions">
        <button class="row-action view-student" data-id="${student.id}" aria-label="View ${escapeHtml(student.first_name)} ${escapeHtml(student.last_name)}" title="View details">↗</button>
        <button class="row-action edit-student" data-id="${student.id}" aria-label="Edit ${escapeHtml(student.first_name)} ${escapeHtml(student.last_name)}" title="Edit student">✎</button>
        <button class="row-action delete delete-student" data-id="${student.id}" aria-label="Delete ${escapeHtml(student.first_name)} ${escapeHtml(student.last_name)}" title="Delete student">×</button>
      </div></td>`;
    rows.append(row);
  });

  const isEmpty = filtered.length === 0;
  emptyState.hidden = !isEmpty;
  document.querySelector("table").hidden = isEmpty;
  document.querySelector("#empty-title").textContent = students.length && query ? "No matching students" : "No students yet";
  document.querySelector("#empty-description").textContent = students.length && query
    ? "Try a different name, email, ID, or course."
    : "Add your first student to get started.";
  document.querySelector("#empty-add").hidden = students.length > 0;
  document.querySelector("#table-summary").textContent = query
    ? `Showing ${filtered.length} of ${students.length} students`
    : `Showing ${students.length} student${students.length === 1 ? "" : "s"}`;
}

async function loadStudents() {
  try {
    const result = await request("/api/students");
    students = result.students;
    renderStudents();
  } catch (error) {
    showToast(error.message);
    throw error;
  }
}

function showToast(message) {
  const toast = document.querySelector("#toast");
  toast.textContent = message;
  toast.classList.add("visible");
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => toast.classList.remove("visible"), 3200);
}

function openForm(student = null) {
  editingId = student?.id ?? null;
  form.reset();
  dialogError.hidden = true;
  document.querySelector("#dialog-title").textContent = editingId ? "Edit student" : "Add a student";
  document.querySelector("#save-student").textContent = editingId ? "Save changes" : "Save student";
  document.querySelector(".dialog-heading p").textContent = editingId
    ? "Update the student information below."
    : "Enter the details below to create a student record.";
  if (student) {
    for (const [name, value] of Object.entries(student)) {
      if (form.elements.namedItem(name)) form.elements.namedItem(name).value = value;
    }
  }
  studentDialog.showModal();
  form.elements.namedItem("student_id").focus();
}

function openDetails(student) {
  document.querySelector("#detail-content").innerHTML = `
    <div class="detail-profile">
      <span class="student-avatar">${escapeHtml(initials(student))}</span>
      <div><h2 id="detail-name">${escapeHtml(student.first_name)} ${escapeHtml(student.last_name)}</h2>
      <p>${escapeHtml(student.student_id)} · <span class="status-pill ${statusClass(student.status)}">${escapeHtml(student.status)}</span></p></div>
    </div>
    <div class="detail-info">
      <div class="detail-field"><span>Email address</span><strong>${escapeHtml(student.email)}</strong></div>
      <div class="detail-field"><span>Course</span><strong>${escapeHtml(student.course)}</strong></div>
      <div class="detail-field"><span>Year of study</span><strong>Year ${escapeHtml(student.year)}</strong></div>
      <div class="detail-field"><span>Student ID</span><strong>${escapeHtml(student.student_id)}</strong></div>
    </div>`;
  detailDialog.showModal();
}

document.querySelector("#add-student").addEventListener("click", () => openForm());
document.querySelector("#empty-add").addEventListener("click", () => openForm());
document.querySelectorAll(".close-dialog").forEach((button) => button.addEventListener("click", () => studentDialog.close()));
document.querySelector(".close-detail").addEventListener("click", () => detailDialog.close());
studentDialog.addEventListener("click", (event) => {
  if (event.target === studentDialog) studentDialog.close();
});
detailDialog.addEventListener("click", (event) => {
  if (event.target === detailDialog) detailDialog.close();
});
searchInput.addEventListener("input", renderStudents);
document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    searchInput.focus();
  }
});

rows.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-id]");
  if (!button) return;
  const id = Number(button.dataset.id);
  const student = students.find((item) => item.id === id);
  if (!student) return;
  if (button.classList.contains("view-student")) {
    openDetails(student);
  } else if (button.classList.contains("edit-student")) {
    openForm(student);
  } else if (button.classList.contains("delete-student")) {
    const fullName = `${student.first_name} ${student.last_name}`;
    if (!window.confirm(`Delete ${fullName}'s student record? This cannot be undone.`)) return;
    button.disabled = true;
    try {
      await request(`/api/students/${id}`, { method: "DELETE" });
      await loadStudents();
      showToast(`${fullName}'s record was deleted.`);
    } catch (error) {
      showToast(error.message);
      button.disabled = false;
    }
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const saveButton = document.querySelector("#save-student");
  const data = Object.fromEntries(new FormData(form).entries());
  data.year = Number(data.year);
  saveButton.disabled = true;
  dialogError.hidden = true;
  try {
    await request(editingId ? `/api/students/${editingId}` : "/api/students", {
      method: editingId ? "PUT" : "POST",
      body: JSON.stringify(data),
    });
    studentDialog.close();
    await loadStudents();
    showToast(editingId ? "Student record updated." : "Student added successfully.");
  } catch (error) {
    dialogError.textContent = error.message;
    dialogError.hidden = false;
  } finally {
    saveButton.disabled = false;
  }
});

document.querySelector("#today-label").textContent = new Intl.DateTimeFormat(undefined, {
  weekday: "short", month: "short", day: "numeric", year: "numeric",
}).format(new Date());
loadStudents();
