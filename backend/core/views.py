from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    def get(self, request):
        return Response(
            {
                "status": "ok",
                "service": "challenge-backend",
                "stage": "mvp-bootstrap",
            }
        )
