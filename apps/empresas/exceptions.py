from rest_framework import status
from rest_framework.exceptions import APIException


class RecursoProtegido(APIException):
    """Se intentó borrar algo con historial asociado (``ON DELETE PROTECT``).

    La respuesta correcta del cliente es inactivar el recurso, no reintentar
    el borrado.
    """

    status_code = status.HTTP_409_CONFLICT
    default_detail = "El recurso tiene registros dependientes y no se puede eliminar."
    default_code = "protegido"
