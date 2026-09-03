class EmpresaQuerysetMixin:
    """Aísla un ``ViewSet`` de negocio al tenant del usuario autenticado.

    Todo ``ViewSet`` que maneje datos de una empresa debe heredar de aquí:

    * ``get_queryset`` filtra automáticamente por ``request.user.empresa``.
    * ``perform_create`` asigna esa misma empresa al crear, de modo que el
      cliente de la API nunca pueda inyectar el ``empresa_id`` de otro tenant
      en el cuerpo de la petición.

    Si aparece un caso no cubierto, se extiende este mixin — nunca se repite
    el filtro por empresa "a mano" en cada vista.
    """

    #: Ruta de lookup hacia la empresa desde el modelo del ViewSet.
    #: Sobrescríbela (p. ej. ``"venta__empresa"``) cuando el modelo no tenga
    #: un campo ``empresa`` directo.
    empresa_lookup = "empresa"

    def get_empresa(self):
        return getattr(self.request.user, "empresa", None)

    def get_queryset(self):
        queryset = super().get_queryset()
        empresa = self.get_empresa()
        if empresa is None:
            return queryset.none()
        return queryset.filter(**{self.empresa_lookup: empresa})

    def perform_create(self, serializer):
        empresa = self.get_empresa()
        if empresa is None:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied(
                "El usuario no está asociado a ninguna empresa."
            )
        serializer.save(**{self.empresa_lookup: empresa})
