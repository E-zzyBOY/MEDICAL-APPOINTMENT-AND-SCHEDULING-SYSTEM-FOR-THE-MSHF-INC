from django.shortcuts import render, get_object_or_404, redirect
from django.http import FileResponse, Http404
from accounts.decorators import role_required
from accounts.models import CustomUser
from .models import MedicalRecords, VitalSign, Prescription


@role_required('patient', 'doctor', 'secretary')
def records_redirect(request):
    if request.user.role == 'patient':
        return redirect('records:patient_records', patient_id=request.user.pk)
    return redirect('landing')


@role_required('patient', 'doctor', 'secretary')
def patient_records_view(request, patient_id):
    patient = get_object_or_404(CustomUser, pk=patient_id, role='patient')
    from django.contrib import messages
    if request.user.role == 'doctor':
        # Doctors have their own records page with its own access checks
        return redirect('doctor:patient_records', patient_id=patient_id)
    if request.user.role == 'secretary':
        # Secretaries have their own limited (vitals-only) records page
        return redirect('secretary:patient_records', patient_id=patient_id)
    if request.user.pk != patient_id:
        messages.error(request, 'Access denied.')
        return redirect('landing')
    records = MedicalRecords.objects.filter(patient=patient).select_related('doctor')
    vitals  = VitalSign.objects.filter(patient=patient).order_by('-date_taken')
    return render(request, 'patient/medical_records.html', {
        'patient': patient, 'records': records, 'vitals': vitals
    })


@role_required('doctor')
def prescription_attachment(request, pk):
    """Streams a prescription attachment instead of letting it be served
    directly from /media/ — these are medical documents (prescription
    scans, lab results), not public assets like profile pictures, so they
    need an ownership check before anyone can view them.

    Allowed: only the doctor who wrote it. Patients receive a signed
    physical prescription at consultation, so prescriptions are never
    shown in patient, secretary, or admin accounts. Any other doctor
    gets a 404 rather than a 403, so this endpoint doesn't even confirm
    whether a given pk has an attachment.
    """
    prescription = get_object_or_404(
        Prescription.objects.select_related('results_consultation__appointment'),
        pk=pk
    )
    appointment = prescription.results_consultation.appointment
    allowed = request.user.pk == appointment.doctor_id
    if not allowed or not prescription.attachment:
        raise Http404('Attachment not found.')

    return FileResponse(
        prescription.attachment.open('rb'),
        filename=prescription.attachment.name.rsplit('/', 1)[-1],
    )
