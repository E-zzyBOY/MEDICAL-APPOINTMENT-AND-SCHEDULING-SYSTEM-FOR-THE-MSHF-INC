# Modal/Pop-up structure — extracted from "UI design for capstone.zip"

Source: `UI design for capstone.zip` (a React + Vite + Tailwind + Radix UI prototype,
not plain HTML). Every "detail/confirm" screen in that prototype is implemented as an
in-page modal instead of a route change, so the URL never updates and no full page
reload happens. This doc captures that structure so it can be ported into this
project's Django + Tailwind templates.

## 1. The repeating pattern (used on every list page)

Every page that needs a detail/confirm view follows the exact same three-part shape:

```tsx
const [selected, setSelected] = React.useState<Appointment | null>(null);
...
<TableRow onClick={() => setSelected(item)} className="cursor-pointer">
  ...
</TableRow>
...
<SomeDetailModal item={selected} onClose={() => setSelected(null)} />
```

1. **State, not a route** — `selected` lives in the page component. There is no
   `navigate()` / `<Link>` to a new URL.
2. **Trigger** — clicking a table row (or a card/button) sets `selected`, which is
   the only thing that opens the modal.
3. **Render** — the modal component is rendered unconditionally at the bottom of the
   page; it returns `null` internally when `item` is `null`, and shows itself via
   `open={!!item}` otherwise. Closing (via the X button, overlay click, or Escape)
   calls `onClose` which sets `selected` back to `null`.

### Pages using this pattern → which modal they open

| Page | Trigger | Modal opened |
|---|---|---|
| `pages/secretary/Appointments.tsx` | click a row in the online/walk-in table | `DoctorAppointmentModal` (Confirm/Decline/Complete buttons live **inside** the modal) |
| `pages/doctor/Appointments.tsx` | click a row in pending/upcoming/past table | `DoctorAppointmentModal` |
| `pages/patient/MyAppointments.tsx` | click an appointment row button | `AppointmentDetailModal` (Cancel button inside) |
| `pages/admin/AllAppointments.tsx` | click a row | `AdminAppointmentModal` (admin-only Cancel) |
| `pages/admin/ManageUsers.tsx` | click a patient/doctor/secretary row | `UserDetailModal` (has its own Edit/Save + Activate/Deactivate inline, no separate edit page) |
| `pages/doctor/MyPatients.tsx`, `pages/secretary/Patients.tsx` | click a patient card/row | `PatientDetailModal` (read-only profile + history) |
| `pages/patient/MedicalRecords.tsx` | click a record row | `RecordDetailModal` (read-only) |

This maps directly onto this project's `appointment_confirm_action.html` /
`appointment_approve` / `appointment_accept` / `appointment_decline` flows, which
currently each do a full page redirect (`/secretary/appointments/<pk>/approve/`,
etc.). The prototype's equivalent is: stay on `appointment_list.html`, open a modal,
POST from inside the modal.

## 2. The actual DOM/HTML structure rendered by the modal

The Radix `Dialog` primitive (`src/components/ui/dialog.tsx`) renders this structure
(simplified to plain HTML, `data-slot` attributes kept since they're useful CSS
hooks):

```html
<!-- DialogPortal -->
<div data-slot="dialog-overlay"
     class="fixed inset-0 z-50 bg-foreground/40 backdrop-blur-[2px]"></div>

<div data-slot="dialog-content"
     role="dialog" aria-modal="true"
     class="fixed top-1/2 left-1/2 z-50 grid w-full max-w-lg -translate-x-1/2 -translate-y-1/2
            gap-4 rounded-xl border border-border bg-card p-6 shadow-lg
            max-h-[88vh] overflow-y-auto">

  <div data-slot="dialog-header" class="flex flex-col gap-1.5 pr-6">
    <h2 data-slot="dialog-title" class="text-lg font-semibold text-foreground">
      Appointment Request
    </h2>
    <p data-slot="dialog-description" class="text-sm text-muted-foreground">
      Reference #123
    </p>
  </div>

  <!-- ...body content: avatar/info rows, <hr> separators, sections... -->

  <div data-slot="dialog-footer" class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
    <button class="btn-outline">Decline</button>
    <button class="btn-primary">Confirm</button>
  </div>

  <button data-slot="dialog-close"
          class="absolute top-4 right-4 rounded-md p-1 text-muted-foreground opacity-80
                 hover:bg-muted hover:opacity-100">
    <svg><!-- X icon --></svg>
  </button>
</div>
```

Key Tailwind classes worth reusing as-is:
- Overlay: `fixed inset-0 z-50 bg-foreground/40 backdrop-blur-[2px]` (swap
  `bg-foreground/40` for `bg-black/40` since this project doesn't have the
  `foreground` custom color token).
- Panel: `fixed top-1/2 left-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2
  rounded-xl border bg-white p-6 shadow-lg max-h-[88vh] overflow-y-auto`.
- Footer buttons: `flex flex-col-reverse gap-2 sm:flex-row sm:justify-end`.

## 3. Body content structure (from `DoctorAppointmentModal.tsx`, the one closest to
this project's secretary/doctor "confirm" use case)

```html
<div class="flex items-center gap-3">
  <!-- avatar -->
  <div class="size-12 rounded-full bg-... flex items-center justify-center">PT</div>
  <div>
    <p class="font-semibold">Patient Name</p>
    <p class="text-sm text-muted-foreground">patient@email.com</p>
  </div>
  <div class="ml-auto"><!-- status badge --></div>
</div>

<hr />

<div class="grid grid-cols-2 gap-4 text-sm">
  <div class="flex items-center gap-2"><!-- calendar icon --> Date</div>
  <div class="flex items-center gap-2"><!-- clock icon --> Time</div>
  <div class="col-span-2"><!-- source badge: Online / Walk-in --></div>
</div>

<hr />

<div>
  <p class="mb-1 text-sm font-semibold">Symptoms</p>
  <p class="text-sm text-muted-foreground">...</p>
</div>

<hr />

<div>
  <p class="mb-2 text-sm font-semibold">Consultation History with This Patient</p>
  <!-- list of past visits with date + status badge -->
</div>

<!-- footer: Decline / Confirm buttons shown only while status === pending -->
```

## 4. Porting notes for this Django project

This project is plain Django templates (no React), so there's no `useState` to
open/close a modal — the equivalent is a hidden `<dialog>`/`<div>` toggled with a
small vanilla JS snippet, while the Confirm/Decline/Cancel buttons keep POSTing to
the existing view (`appointment_approve`, `appointment_decline`, etc.) via a normal
`<form method="post">` inside the modal — only the *navigation* changes, not the
view/permission logic already in `appointments/views/`.

Minimal vanilla-JS toggle (no extra dependency needed):

```html
<button onclick="document.getElementById('apt-modal-{{ appt.pk }}').showModal()">
  {{ appt.patient.get_full_name }}
</button>

<dialog id="apt-modal-{{ appt.pk }}" class="rounded-xl p-6 max-w-lg w-full backdrop:bg-black/40">
  ...modal content (reuse appointment_confirm_action.html's body)...
  <form method="post" action="/secretary/appointments/{{ appt.pk }}/approve/">
    {% csrf_token %}
    <button type="submit">Confirm</button>
    <button type="button" onclick="this.closest('dialog').close()">Cancel</button>
  </form>
</dialog>
```

The native `<dialog>` element gives the overlay + centering + Escape-to-close for
free, matching the prototype's behavior without pulling in Radix/React.
