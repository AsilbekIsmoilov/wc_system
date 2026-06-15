"""
DRF-ViewSet'ы и APIView для hourly_locks.
"""

import logging
from datetime import date, datetime, timedelta

from django.db.models import Q
from django.utils.timezone import now
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .filters import (
    CompensationFilter,
    EventLogFilter,
    ManualAdjustmentFilter,
    OperatorScheduleDayFilter,
    TransferFilter,
    WorkDebtDetailFilter,
    WorkLogDailyFilter,
)
from .models import (
    AutomationOverride,
    Compensation,
    Cycle,
    EventLog,
    Group,
    ManualAdjustment,
    Note,
    Operator,
    OperatorScheduleDay,
    RequestTypeRule,
    Shift,
    SystemPolicy,
    Transfer,
    User,
    WorkDebt,
    WorkDebtDetail,
    WorkLogDaily,
)
from .pagination import LargePagination, StandardPagination, TransferPagination
from .permissions import (
    CanCloseCycle,
    CanManualAdjust,
    IsManagerOrAdmin,
    IsSupervisorOrHigher,
    ReadOnlyOrManager,
)
from .serializers import (
    AutomationOverrideSerializer,
    CompensationDetailSerializer,
    CompensationSerializer,
    CycleSerializer,
    EventLogSerializer,
    GroupSerializer,
    ManualAdjustmentSerializer,
    MyTokenObtainPairSerializer,
    NoteSerializer,
    OperatorScheduleDaySerializer,
    OperatorSerializer,
    RequestTypeRuleSerializer,
    RetroactiveCheckRequestSerializer,
    ShiftSerializer,
    SystemPolicySerializer,
    TransferSerializer,
    UserMeSerializer,
    WorkDebtDetailSerializer,
    WorkDebtDetailShortSerializer,
    WorkDebtListLightSerializer,
    WorkDebtSerializer,
    WorkLogDailySerializer,
)

logger = logging.getLogger(__name__)


# =============================================================================
# JWT и Me
# =============================================================================

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = (
            User.objects
            .select_related("operator", "operator__group")
            .prefetch_related("supervised_groups")
            .get(pk=request.user.id)
        )
        return Response(UserMeSerializer(user).data)


# =============================================================================
# Operator / Group
# =============================================================================

class OperatorViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = OperatorSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ["surname", "name", "middle_name", "login_id"]
    pagination_class = StandardPagination

    def get_queryset(self):
        user = self.request.user
        qs = Operator.objects.filter(is_active=True).select_related("group")

        if user.role == "operator":
            op = getattr(user, "operator", None)
            qs = qs.filter(id=op.id) if op else qs.none()
        elif user.role == "supervisor":
            op = getattr(user, "operator", None)
            if op:
                group_ids = user.supervised_groups.values_list("id", flat=True)
                qs = qs.filter(group_id__in=group_ids)
            else:
                qs = qs.none()

        return qs.order_by("surname", "name")


class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.filter(is_active=True).select_related("supervisor")
    serializer_class = GroupSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination


# =============================================================================
# Shift
# =============================================================================

class ShiftViewSet(viewsets.ModelViewSet):
    queryset = Shift.objects.all().order_by("code")
    serializer_class = ShiftSerializer
    permission_classes = [ReadOnlyOrManager]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ["code", "display_name"]
    filterset_fields = ["is_active", "is_night", "requires_special_pipeline"]


# =============================================================================
# OperatorScheduleDay
# =============================================================================

class OperatorScheduleDayViewSet(viewsets.ModelViewSet):
    serializer_class = OperatorScheduleDaySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = OperatorScheduleDayFilter
    pagination_class = StandardPagination

    def get_queryset(self):
        user = self.request.user
        qs = OperatorScheduleDay.objects.select_related(
            "operator", "operator__group", "shift",
        ).order_by("-day")

        if user.role == "operator":
            op = getattr(user, "operator", None)
            qs = qs.filter(operator=op) if op else qs.none()
        elif user.role == "supervisor":
            group_ids = user.supervised_groups.values_list("id", flat=True)
            qs = qs.filter(operator__group_id__in=group_ids)

        return qs


# =============================================================================
# Cycle
# =============================================================================

class CycleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Cycle.objects.all().order_by("-year", "-month")
    serializer_class = CycleSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    @action(detail=False, methods=["get"], url_path="active")
    def active(self, request):
        """Возвращает текущий активный цикл."""
        active_cycle = Cycle.get_active()
        if not active_cycle:
            return Response({"detail": "Активный цикл не найден"}, status=404)
        return Response(self.get_serializer(active_cycle).data)

    @action(
        detail=True, methods=["post"],
        url_path="close", permission_classes=[CanCloseCycle],
    )
    def close(self, request, pk=None):
        """Ручное закрытие цикла (только manager/admin)."""
        from .services.cycle import close_cycle

        cycle = self.get_object()
        if cycle.status == "closed":
            return Response(
                {"detail": "Цикл уже закрыт"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = close_cycle(cycle, user=request.user)
        return Response(result)


# =============================================================================
# RequestTypeRule / SystemPolicy
# =============================================================================

class RequestTypeRuleViewSet(viewsets.ModelViewSet):
    queryset = RequestTypeRule.objects.all().order_by("category", "sort_order")
    serializer_class = RequestTypeRuleSerializer
    permission_classes = [ReadOnlyOrManager]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["category", "is_active", "verification_strategy"]


class SystemPolicyViewSet(viewsets.ModelViewSet):
    queryset = SystemPolicy.objects.all().order_by("key")
    serializer_class = SystemPolicySerializer
    permission_classes = [IsManagerOrAdmin]

    def perform_create(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


# =============================================================================
# WorkLogDaily
# =============================================================================

class WorkLogDailyViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WorkLogDailySerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = WorkLogDailyFilter
    pagination_class = StandardPagination

    def get_queryset(self):
        user = self.request.user
        qs = WorkLogDaily.objects.select_related(
            "operator", "operator__group", "shift", "cycle",
        ).order_by("-day")

        if user.role == "operator":
            op = getattr(user, "operator", None)
            qs = qs.filter(operator=op) if op else qs.none()
        elif user.role == "supervisor":
            group_ids = user.supervised_groups.values_list("id", flat=True)
            qs = qs.filter(operator__group_id__in=group_ids)

        return qs


# =============================================================================
# WorkDebt / WorkDebtDetail
# =============================================================================

class WorkDebtViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WorkDebtSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["operator", "cycle"]
    pagination_class = StandardPagination

    def get_queryset(self):
        user = self.request.user
        qs = WorkDebt.objects.select_related(
            "operator", "operator__group", "cycle",
        )

        if user.role == "operator":
            op = getattr(user, "operator", None)
            qs = qs.filter(operator=op) if op else qs.none()
        elif user.role == "supervisor":
            group_ids = user.supervised_groups.values_list("id", flat=True)
            qs = qs.filter(operator__group_id__in=group_ids)

        return qs.order_by("operator__surname")

    @action(detail=False, methods=["get"], url_path="light")
    def light(self, request):
        """Облегчённый список (для главного экрана)."""
        qs = self.get_queryset()
        serializer = WorkDebtListLightSerializer(
            qs, many=True, context={"request": request},
        )
        return Response(serializer.data)


class WorkDebtDetailViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WorkDebtDetailSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = WorkDebtDetailFilter
    pagination_class = StandardPagination

    def get_queryset(self):
        user = self.request.user
        qs = WorkDebtDetail.objects.select_related(
            "operator", "operator__group", "shift", "cycle",
        ).order_by("-day")

        if user.role == "operator":
            op = getattr(user, "operator", None)
            qs = qs.filter(operator=op) if op else qs.none()
        elif user.role == "supervisor":
            group_ids = user.supervised_groups.values_list("id", flat=True)
            qs = qs.filter(operator__group_id__in=group_ids)

        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return WorkDebtDetailShortSerializer
        return WorkDebtDetailSerializer


# =============================================================================
# Compensation
# =============================================================================

class CompensationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    parser_classes = (JSONParser, MultiPartParser, FormParser)
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = CompensationFilter
    search_fields = [
        "operator__surname", "operator__name", "operator__login_id",
        "comment",
    ]
    ordering_fields = ["planned_date", "created_at", "status"]
    pagination_class = TransferPagination

    def get_queryset(self):
        user = self.request.user
        qs = Compensation.objects.select_related(
            "operator", "operator__group", "type_rule", "cycle",
            "fixed_by", "verified_by",
        ).prefetch_related("debt_links__debt_detail")

        if user.role == "operator":
            op = getattr(user, "operator", None)
            qs = qs.filter(operator=op) if op else qs.none()
        elif user.role == "supervisor":
            group_ids = user.supervised_groups.values_list("id", flat=True)
            qs = qs.filter(operator__group_id__in=group_ids)

        return qs.order_by("-planned_date", "-created_at")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return CompensationDetailSerializer
        return CompensationSerializer

    def perform_create(self, serializer):
        from .services.compensation_verifier import verify_single_compensation
        from .services.cycle import get_or_create_active_cycle

        comp = serializer.save()

        # Если тип имеет auto_approve_on_create — обрабатываем
        rule = comp.type_rule
        if rule.auto_approve_on_create:
            cycle = get_or_create_active_cycle()
            verify_single_compensation(comp, comp.planned_date, cycle)


# =============================================================================
# Ретроактивная проверка
# =============================================================================

class RetroactiveCompensationCheckView(APIView):
    """
    Ретроактивная проверка: оператор уже отработал, теперь подаёт заявку.
    Создаёт Compensation с source='retroactive' и запускает авто-проверку.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RetroactiveCheckRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            operator = Operator.objects.get(id=data["operator_id"])
            rule = RequestTypeRule.objects.get(
                code=data["type_rule_code"],
                category="compensation",
                is_active=True,
            )
        except (Operator.DoesNotExist, RequestTypeRule.DoesNotExist):
            return Response(
                {"detail": "Оператор или тип не найден"},
                status=status.HTTP_404_NOT_FOUND,
            )

        from .services.cycle import get_or_create_active_cycle
        from .services.retroactive_check import auto_check_retroactive

        cycle = get_or_create_active_cycle()

        # Проверка прав
        if request.user.role == "operator":
            op = getattr(request.user, "operator", None)
            if not op or op.id != operator.id:
                return Response(
                    {"detail": "Нельзя создавать заявку для другого оператора"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        comp = Compensation(
            operator=operator,
            cycle=cycle,
            type_rule=rule,
            source="retroactive",
            planned_date=data["planned_date"],
            requested_duration=data["requested_duration"],
            comment=data.get("reason_text", ""),
            claim_metadata={
                "reason_text": data.get("reason_text", ""),
                "witnesses": data.get("witnesses", ""),
                "submitted_by_user_id": request.user.id,
            },
            fixed_by=request.user,
            status="pending",
        )

        try:
            comp.full_clean()
            comp.save()
        except Exception as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Запуск авто-проверки
        auto_check_retroactive(comp, data["planned_date"], cycle)

        # Возвращаем результат
        comp.refresh_from_db()
        return Response(
            CompensationDetailSerializer(comp, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


# =============================================================================
# Transfer
# =============================================================================

class TransferViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    parser_classes = (JSONParser, MultiPartParser, FormParser)
    serializer_class = TransferSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = TransferFilter
    search_fields = [
        "operator__surname", "operator__name", "operator__login_id",
        "comment",
    ]
    ordering_fields = ["date_from", "date_to", "created_at"]
    pagination_class = TransferPagination

    def get_queryset(self):
        user = self.request.user
        qs = Transfer.objects.select_related(
            "operator", "operator__group", "type_rule", "cycle", "fixed_by",
        )

        if user.role == "operator":
            op = getattr(user, "operator", None)
            qs = qs.filter(operator=op) if op else qs.none()
        elif user.role == "supervisor":
            group_ids = user.supervised_groups.values_list("id", flat=True)
            qs = qs.filter(operator__group_id__in=group_ids)

        return qs.order_by("-created_at")


# =============================================================================
# ManualAdjustment
# =============================================================================

class ManualAdjustmentViewSet(viewsets.ModelViewSet):
    serializer_class = ManualAdjustmentSerializer
    permission_classes = [CanManualAdjust]
    filter_backends = [DjangoFilterBackend]
    filterset_class = ManualAdjustmentFilter
    pagination_class = StandardPagination

    def get_queryset(self):
        user = self.request.user
        qs = ManualAdjustment.objects.select_related(
            "operator", "adjusted_by", "approved_by",
        )

        if user.role == "supervisor":
            op = getattr(user, "operator", None)
            if op:
                group_ids = user.supervised_groups.values_list("id", flat=True)
                qs = qs.filter(operator__group_id__in=group_ids)
            else:
                qs = qs.none()

        return qs.order_by("-adjusted_at")

    def perform_create(self, serializer):
        serializer.save(adjusted_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        from .services.manual_adjustment import approve_adjustment

        adjustment = self.get_object()
        try:
            approve_adjustment(adjustment, request.user)
            return Response({"status": "approved"})
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )


# =============================================================================
# AutomationOverride
# =============================================================================

class AutomationOverrideViewSet(viewsets.ModelViewSet):
    queryset = AutomationOverride.objects.select_related(
        "operator", "created_by", "deactivated_by",
    )
    serializer_class = AutomationOverrideSerializer
    permission_classes = [IsManagerOrAdmin]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["operator", "override_type", "is_active"]
    pagination_class = StandardPagination

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, pk=None):
        override = self.get_object()
        override.is_active = False
        override.deactivated_at = now()
        override.deactivated_by = request.user
        override.save(update_fields=[
            "is_active", "deactivated_at", "deactivated_by",
        ])
        return Response({"status": "deactivated"})


# =============================================================================
# Note / EventLog / Logos
# =============================================================================

class NoteViewSet(viewsets.ModelViewSet):
    serializer_class = NoteSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["target_type", "target_id", "visibility"]
    pagination_class = StandardPagination

    def get_queryset(self):
        user = self.request.user
        qs = Note.objects.select_related("created_by").order_by("-created_at")

        # Фильтрация по видимости
        if user.role == "operator":
            qs = qs.filter(visibility__in=["public", "operator"])
        elif user.role == "supervisor":
            qs = qs.filter(visibility__in=["public", "operator", "supervisor"])

        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class EventLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = EventLog.objects.all().select_related("operator", "triggered_by")
    serializer_class = EventLogSerializer
    permission_classes = [IsManagerOrAdmin]
    filter_backends = [DjangoFilterBackend]
    filterset_class = EventLogFilter
    pagination_class = LargePagination
    ordering = ["-timestamp"]
