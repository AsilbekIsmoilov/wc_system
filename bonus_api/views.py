# from rest_framework import status
#
# from rest_framework.views import APIView
# from rest_framework.response import Response
# from hourly_locks.models import WorkCompensation
# from .services.compensation import calculate_deduction_preview
# from .serializers import DeductionPreviewSerializer
# from datetime import datetime
#
#
# class CalculateAPIView(APIView):
#     def get(self, request):
#         try:
#             raw_data = calculate_deduction_preview()
#
#             serializer = DeductionPreviewSerializer(raw_data)
#
#             return Response(serializer.data, status=status.HTTP_200_OK)
#
#         except Exception as e:
#             return Response(
#                 {"error": str(e)},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )
#
#
#
# class DailyApprovedCompensationDetailAPIView(APIView):
#     def get(self, request):
#         date_str = request.GET.get("date")
#
#         if not date_str:
#             return Response({"error": "date parameter is required (YYYY-MM-DD)"}, status=400)
#
#         try:
#             target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
#         except ValueError:
#             return Response({"error": "Invalid date format. Use YYYY-MM-DD"}, status=400)
#
#         allowed_types = [
#             "sl",
#             "wc",
#             "study",
#             "vacation",
#             "exception",
#             "partial_exception",
#         ]
#
#         qs = (
#             WorkCompensation.objects
#             .filter(
#                 planned_date=target_date,
#                 status="approved",
#                 type__in=allowed_types
#             )
#             .select_related("operator")
#             .order_by("operator__surname", "operator__name")
#         )
#
#         data = []
#         for obj in qs:
#             duration = obj.duration
#             total_seconds = int(duration.total_seconds()) if duration else 0
#
#             hours = total_seconds // 3600
#             minutes = (total_seconds % 3600) // 60
#             seconds = total_seconds % 60
#
#             data.append({
#                 "operator_id": obj.operator_id,
#                 "surname": obj.operator.surname,
#                 "name": obj.operator.name,
#                 "middle_name": obj.operator.middle_name,
#                 "login_id": obj.operator.login_id,
#
#                 "planned_date": obj.planned_date,
#
#                 "type": obj.type,
#                 "status": obj.status,
#
#                 "duration": f"{hours:02d}:{minutes:02d}:{seconds:02d}",
#
#                 "note": obj.comment,
#                 "created_at": obj.created_at,
#             })
#
#         return Response({
#             "date": target_date,
#             "count": len(data),
#             "results": data
#         })