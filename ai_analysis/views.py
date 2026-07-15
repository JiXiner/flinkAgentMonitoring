from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .analyzer import answer_question
from .scheduler import execute_inspection


class JixChatView(APIView):
    def post(self, request):
        question = str(request.data.get("question", "")).strip()
        if not question:
            return Response({"detail": "请输入问题。"}, status=status.HTTP_400_BAD_REQUEST)
        if len(question) > 2000:
            return Response({"detail": "问题长度不能超过 2000 字。"}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"answer": answer_question(question)})


class JixInspectionView(APIView):
    def post(self, request):
        return Response(execute_inspection())
