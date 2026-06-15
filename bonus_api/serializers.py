from rest_framework import serializers


class OperatorSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    surname = serializers.CharField(allow_null=True, allow_blank=True)
    name = serializers.CharField(allow_null=True, allow_blank=True)
    middle_name = serializers.CharField(allow_null=True, allow_blank=True)
    full_name = serializers.CharField(allow_null=True, allow_blank=True)
    login_id = serializers.CharField(allow_null=True, allow_blank=True)
    group = serializers.CharField(allow_null=True, allow_blank=True)


class DeductionPreviewItemSerializer(serializers.Serializer):
    operator = OperatorSerializer()
    total_debt_accumulated = serializers.CharField(help_text="HH:MM:SS")
    system_error_duration = serializers.CharField(help_text="HH:MM:SS")
    after_deduction = serializers.CharField(help_text="HH:MM:SS")
    compensation_total = serializers.CharField(required=False, allow_null=True)
    compensation_declined_total = serializers.CharField(required=False, allow_null=True)
    no_compensation_total = serializers.CharField(required=False, allow_null=True)


class DeductionPreviewSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    data = DeductionPreviewItemSerializer(many=True)