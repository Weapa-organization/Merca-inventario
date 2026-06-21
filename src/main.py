from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import flet as ft


APP_TITLE = "Merca-inventario"
DATA_FILE_NAME = "shopping_lists.json"
DATA_VERSION = 2
CARD_DRAG_THRESHOLD = 70


class JsonStorage:
    """Guarda todas las listas y ajustes en un único archivo JSON local."""

    def __init__(self) -> None:
        self.file_path = self._get_storage_directory() / DATA_FILE_NAME

    @staticmethod
    def _get_storage_directory() -> Path:
        # En Android, Flet proporciona una carpeta privada y persistente.
        android_storage = os.getenv("FLET_APP_STORAGE_DATA")
        if android_storage:
            directory = Path(android_storage)
        else:
            # Carpeta usada al desarrollar desde el ordenador.
            directory = Path(__file__).resolve().parents[1] / "storage" / "data"

        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def load(self) -> dict[str, Any]:
        if not self.file_path.exists():
            return self.empty_data()

        try:
            with self.file_path.open("r", encoding="utf-8") as file:
                data = json.load(file)

            if not isinstance(data, dict) or not isinstance(data.get("lists"), list):
                raise ValueError("El archivo JSON no tiene el formato esperado.")

            return data
        except (OSError, json.JSONDecodeError, ValueError):
            # Conservamos una copia del archivo dañado antes de empezar uno nuevo.
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            damaged_file = self.file_path.with_name(
                f"shopping_lists_corrupt_{timestamp}.json"
            )
            try:
                self.file_path.replace(damaged_file)
            except OSError:
                pass
            return self.empty_data()

    @staticmethod
    def empty_data() -> dict[str, Any]:
        return {
            "version": DATA_VERSION,
            "settings": {"dark_mode": False},
            "lists": [],
        }

    def save(self, data: dict[str, Any]) -> None:
        # Escritura atómica: primero se escribe un temporal y después se reemplaza.
        temporary_file = self.file_path.with_suffix(".tmp")
        with temporary_file.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        temporary_file.replace(self.file_path)


class ShoppingListApp:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.storage = JsonStorage()
        self.data = self.storage.load()
        self.current_index = 0
        self.card_drag_distance = 0.0

        self._migrate_data()
        self.dark_mode = bool(self.data["settings"].get("dark_mode", False))

        self.dark_mode_button = ft.IconButton(
            icon=self._theme_icon(),
            tooltip=self._theme_tooltip(),
            on_click=self.toggle_dark_mode,
        )
        self.new_list_button = ft.IconButton(
            icon=ft.Icons.ADD,
            tooltip="Crear una nueva lista",
            on_click=self.show_new_list_dialog,
        )
        self.previous_button = ft.IconButton(
            icon=ft.Icons.ARROW_BACK_IOS_NEW,
            tooltip="Lista anterior",
            on_click=self.show_previous_list,
        )
        self.page_indicator = ft.Text(
            "1 / 1",
            weight=ft.FontWeight.W_600,
            text_align=ft.TextAlign.CENTER,
        )
        self.next_button = ft.IconButton(
            icon=ft.Icons.ARROW_FORWARD_IOS,
            tooltip="Lista siguiente",
            on_click=self.show_next_list,
        )

        self.page_view = ft.PageView(
            expand=True,
            horizontal=True,
            viewport_fraction=0.92,
            snap=True,
            pad_ends=True,
            implicit_scrolling=True,
            keep_page=True,
            on_change=self._on_page_changed,
        )

        self._configure_page()
        self._ensure_first_list()
        self.refresh()

    def _migrate_data(self) -> None:
        """Adapta automáticamente archivos creados por versiones anteriores."""
        changed = False

        if not isinstance(self.data.get("settings"), dict):
            self.data["settings"] = {}
            changed = True

        if "dark_mode" not in self.data["settings"]:
            self.data["settings"]["dark_mode"] = False
            changed = True

        if self.data.get("version") != DATA_VERSION:
            self.data["version"] = DATA_VERSION
            changed = True

        for shopping_list in self.data.get("lists", []):
            if not shopping_list.get("id"):
                shopping_list["id"] = uuid4().hex
                changed = True

            if not isinstance(shopping_list.get("items"), list):
                shopping_list["items"] = []
                changed = True

            for item in shopping_list["items"]:
                if not item.get("id"):
                    item["id"] = uuid4().hex
                    changed = True
                if item.get("type") not in {"check", "note"}:
                    item["type"] = "check"
                    changed = True
                if "text" not in item:
                    item["text"] = ""
                    changed = True
                if "checked" not in item:
                    item["checked"] = False
                    changed = True

        if changed:
            self.storage.save(self.data)

    def _configure_page(self) -> None:
        self.page.title = APP_TITLE
        self.page.padding = 0
        self.page.theme_mode = (
            ft.ThemeMode.DARK if self.dark_mode else ft.ThemeMode.LIGHT
        )
        self.page.theme = ft.Theme(color_scheme_seed=ft.Colors.GREEN)
        self.page.dark_theme = ft.Theme(color_scheme_seed=ft.Colors.GREEN)
        self.page.appbar = ft.AppBar(
            leading=self.new_list_button,
            leading_width=56,
            title=ft.Text(APP_TITLE),
            center_title=True,
            actions=[self.dark_mode_button],
            actions_padding=8,
        )

        navigation_bar = ft.Container(
            padding=ft.Padding.only(left=16, right=16, top=2, bottom=8),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    self.previous_button,
                    ft.Container(
                        width=90,
                        alignment=ft.Alignment.CENTER,
                        content=self.page_indicator,
                    ),
                    self.next_button,
                ],
            ),
        )

        self.page.add(
            ft.SafeArea(
                expand=True,
                content=ft.Column(
                    expand=True,
                    spacing=0,
                    controls=[self.page_view, navigation_bar],
                ),
            )
        )

    @property
    def shopping_lists(self) -> list[dict[str, Any]]:
        return self.data["lists"]

    def _ensure_first_list(self) -> None:
        if self.shopping_lists:
            return

        self.shopping_lists.append(
            self._new_list_data(
                title=f"Compra {datetime.now().strftime('%d/%m/%Y')}"
            )
        )
        self.storage.save(self.data)

    @staticmethod
    def _new_list_data(title: str) -> dict[str, Any]:
        now = datetime.now().isoformat(timespec="seconds")
        return {
            "id": uuid4().hex,
            "title": title,
            "created_at": now,
            "items": [],
        }

    def _theme_icon(self) -> str:
        return ft.Icons.LIGHT_MODE if self.dark_mode else ft.Icons.DARK_MODE

    def _theme_tooltip(self) -> str:
        return "Activar modo claro" if self.dark_mode else "Activar modo oscuro"

    def toggle_dark_mode(self, _: ft.Event[Any]) -> None:
        self.dark_mode = not self.dark_mode
        self.data["settings"]["dark_mode"] = self.dark_mode
        self.storage.save(self.data)

        self.page.theme_mode = (
            ft.ThemeMode.DARK if self.dark_mode else ft.ThemeMode.LIGHT
        )
        self.dark_mode_button.icon = self._theme_icon()
        self.dark_mode_button.tooltip = self._theme_tooltip()
        self.page.update()

    def _on_page_changed(self, event: ft.Event[ft.PageView]) -> None:
        try:
            self.current_index = int(event.data)
        except (TypeError, ValueError):
            self.current_index = 0

        self._update_navigation()
        self.page.update()

    def _update_navigation(self) -> None:
        total = len(self.shopping_lists)
        if total == 0:
            self.current_index = 0
            self.page_indicator.value = "0 / 0"
            self.previous_button.disabled = True
            self.next_button.disabled = True
            return

        self.current_index = min(max(self.current_index, 0), total - 1)
        self.page_indicator.value = f"{self.current_index + 1} / {total}"
        self.previous_button.disabled = self.current_index <= 0
        self.next_button.disabled = self.current_index >= total - 1

    async def show_previous_list(self, _: ft.Event[Any] | None = None) -> None:
        if self.current_index <= 0:
            return
        await self.page_view.previous_page(
            animation_duration=ft.Duration(milliseconds=250),
            animation_curve=ft.AnimationCurve.EASE_OUT,
        )

    async def show_next_list(self, _: ft.Event[Any] | None = None) -> None:
        if self.current_index >= len(self.shopping_lists) - 1:
            return
        await self.page_view.next_page(
            animation_duration=ft.Duration(milliseconds=250),
            animation_curve=ft.AnimationCurve.EASE_OUT,
        )

    def _start_card_drag(self, _: ft.DragStartEvent) -> None:
        self.card_drag_distance = 0.0

    def _update_card_drag(self, event: ft.DragUpdateEvent) -> None:
        self.card_drag_distance += float(event.local_delta.x)

    async def _finish_card_drag(self, _: ft.DragEndEvent) -> None:
        drag_distance = self.card_drag_distance
        self.card_drag_distance = 0.0

        if drag_distance >= CARD_DRAG_THRESHOLD:
            await self.show_previous_list()
        elif drag_distance <= -CARD_DRAG_THRESHOLD:
            await self.show_next_list()

    def refresh(self, selected_list_id: str | None = None) -> None:
        if selected_list_id:
            selected_index = next(
                (
                    index
                    for index, shopping_list in enumerate(self.shopping_lists)
                    if shopping_list["id"] == selected_list_id
                ),
                0,
            )
        else:
            selected_index = min(
                self.current_index,
                max(len(self.shopping_lists) - 1, 0),
            )

        self.current_index = selected_index
        self.page_view.controls = [
            self._build_list_card(shopping_list)
            for shopping_list in self.shopping_lists
        ]
        self.page_view.selected_index = selected_index
        self._update_navigation()
        self.page.update()

    @staticmethod
    def _format_date(value: str) -> str:
        try:
            return datetime.fromisoformat(value).strftime("%d/%m/%Y · %H:%M")
        except ValueError:
            return value

    def _find_list(self, list_id: str) -> dict[str, Any] | None:
        return next(
            (
                shopping_list
                for shopping_list in self.shopping_lists
                if shopping_list["id"] == list_id
            ),
            None,
        )

    @staticmethod
    def _find_item(
        shopping_list: dict[str, Any], item_id: str
    ) -> dict[str, Any] | None:
        return next(
            (item for item in shopping_list.get("items", []) if item["id"] == item_id),
            None,
        )

    def _show_message(self, message: str) -> None:
        self.page.show_dialog(ft.SnackBar(content=ft.Text(message)))

    def _add_item(
        self,
        list_id: str,
        text_field: ft.TextField,
        note_checkbox: ft.Checkbox,
    ) -> None:
        content = (text_field.value or "").strip()
        if not content:
            self._show_message("Escribe un producto o una nota.")
            return

        shopping_list = self._find_list(list_id)
        if shopping_list is None:
            return

        shopping_list["items"].append(
            {
                "id": uuid4().hex,
                "type": "note" if note_checkbox.value else "check",
                "text": content,
                "checked": False,
            }
        )
        self.storage.save(self.data)
        self.refresh(selected_list_id=list_id)

    def _toggle_item(self, list_id: str, item_id: str, checked: bool) -> None:
        shopping_list = self._find_list(list_id)
        if shopping_list is None:
            return

        item = self._find_item(shopping_list, item_id)
        if item is None:
            return

        item["checked"] = checked
        self.storage.save(self.data)
        self.refresh(selected_list_id=list_id)

    def _delete_item(self, list_id: str, item_id: str) -> None:
        shopping_list = self._find_list(list_id)
        if shopping_list is None:
            return

        shopping_list["items"] = [
            item for item in shopping_list["items"] if item["id"] != item_id
        ]
        self.storage.save(self.data)
        self.refresh(selected_list_id=list_id)

    def _reorder_items(self, list_id: str, event: ft.OnReorderEvent) -> None:
        shopping_list = self._find_list(list_id)
        if shopping_list is None:
            return

        items = shopping_list["items"]
        old_index = event.old_index
        new_index = event.new_index

        if not (0 <= old_index < len(items)):
            return

        moved_item = items.pop(old_index)
        items.insert(new_index, moved_item)
        self.storage.save(self.data)

        # Flet no reordena automáticamente la colección de controles.
        moved_control = event.control.controls.pop(old_index)
        event.control.controls.insert(new_index, moved_control)
        event.control.update()

    def show_edit_item_dialog(self, list_id: str, item_id: str) -> None:
        shopping_list = self._find_list(list_id)
        if shopping_list is None:
            return

        item = self._find_item(shopping_list, item_id)
        if item is None:
            return

        is_note = item.get("type") == "note"
        text_field = ft.TextField(
            label="Texto de la nota" if is_note else "Texto del producto",
            value=item.get("text", ""),
            autofocus=True,
            capitalization=ft.TextCapitalization.SENTENCES,
        )

        def save_edit(_: ft.Event[Any]) -> None:
            new_text = (text_field.value or "").strip()
            if not new_text:
                self._show_message("El texto no puede quedar vacío.")
                return

            item["text"] = new_text
            self.storage.save(self.data)
            self.page.pop_dialog()
            self.refresh(selected_list_id=list_id)

        text_field.on_submit = save_edit

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Editar nota" if is_note else "Editar producto"),
                content=text_field,
                actions=[
                    ft.TextButton(
                        "Cancelar",
                        on_click=lambda e: self.page.pop_dialog(),
                    ),
                    ft.FilledButton("Guardar", on_click=save_edit),
                ],
            )
        )

    def _build_item(self, list_id: str, item: dict[str, Any]) -> ft.Control:
        item_id = item["id"]
        content = item.get("text", "")
        is_note = item.get("type") == "note"
        checked = bool(item.get("checked", False))

        drag_handle = ft.ReorderableDragHandle(
            key=f"drag_{item_id}",
            mouse_cursor=ft.MouseCursor.GRAB,
            content=ft.Container(
                padding=ft.Padding.symmetric(horizontal=4, vertical=10),
                content=ft.Icon(ft.Icons.DRAG_INDICATOR, size=22),
            ),
        )

        leading_control: ft.Control
        if is_note:
            leading_control = ft.Icon(ft.Icons.NOTES, size=22)
        else:
            leading_control = ft.Checkbox(
                value=checked,
                on_change=lambda e, iid=item_id: self._toggle_item(
                    list_id,
                    iid,
                    bool(e.control.value),
                ),
            )

        text_style = (
            ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH)
            if checked and not is_note
            else None
        )

        return ft.Container(
            key=f"item_{item_id}",
            padding=ft.Padding.symmetric(horizontal=2, vertical=2),
            border_radius=8,
            content=ft.Row(
                spacing=2,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    drag_handle,
                    leading_control,
                    ft.Text(content, expand=True, style=text_style),
                    ft.IconButton(
                        icon=ft.Icons.EDIT_OUTLINED,
                        tooltip="Editar nota" if is_note else "Editar producto",
                        on_click=lambda e, iid=item_id: self.show_edit_item_dialog(
                            list_id, iid
                        ),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        tooltip="Eliminar nota" if is_note else "Eliminar producto",
                        on_click=lambda e, iid=item_id: self._delete_item(
                            list_id, iid
                        ),
                    ),
                ],
            ),
        )

    def _build_list_card(self, shopping_list: dict[str, Any]) -> ft.Control:
        list_id = shopping_list["id"]
        items = shopping_list.get("items", [])
        completed = sum(
            1
            for item in items
            if item.get("type") == "check" and item.get("checked")
        )
        checkable_items = sum(1 for item in items if item.get("type") == "check")

        if items:
            items_view: ft.Control = ft.ReorderableListView(
                expand=True,
                spacing=2,
                padding=0,
                show_default_drag_handles=False,
                mouse_cursor=ft.MouseCursor.GRAB,
                on_reorder=lambda e: self._reorder_items(list_id, e),
                controls=[self._build_item(list_id, item) for item in items],
            )
        else:
            items_view = ft.Container(
                expand=True,
                alignment=ft.Alignment.CENTER,
                padding=30,
                content=ft.Column(
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(ft.Icons.SHOPPING_BASKET_OUTLINED, size=48),
                        ft.Text("La lista está vacía."),
                        ft.Text(
                            "Añade el primer producto en la parte inferior.",
                            size=12,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                ),
            )

        text_field = ft.TextField(
            hint_text="Producto o nota",
            expand=True,
            capitalization=ft.TextCapitalization.SENTENCES,
        )
        note_checkbox = ft.Checkbox(label="Nota", value=False)

        def add_item(_: ft.Event[Any]) -> None:
            self._add_item(list_id, text_field, note_checkbox)

        text_field.on_submit = add_item

        header_content = ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Icon(ft.Icons.SHOPPING_CART_OUTLINED, size=30),
                ft.Column(
                    expand=True,
                    spacing=2,
                    controls=[
                        ft.Text(
                            shopping_list["title"],
                            size=21,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            self._format_date(shopping_list["created_at"]),
                            size=12,
                        ),
                        ft.Text(
                            f"{completed} de {checkable_items} productos comprados",
                            size=12,
                        ),
                    ],
                ),
                ft.IconButton(
                    icon=ft.Icons.EDIT_OUTLINED,
                    tooltip="Editar título de la lista",
                    on_click=lambda e: self.show_edit_list_title_dialog(list_id),
                ),
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    tooltip="Eliminar esta lista",
                    on_click=lambda e: self.show_delete_list_dialog(list_id),
                ),
            ],
        )

        # Permite cambiar de tarjeta arrastrando la cabecera con el ratón.
        header = ft.GestureDetector(
            mouse_cursor=ft.MouseCursor.GRAB,
            drag_interval=10,
            on_horizontal_drag_start=self._start_card_drag,
            on_horizontal_drag_update=self._update_card_drag,
            on_horizontal_drag_end=self._finish_card_drag,
            content=header_content,
        )

        card_content = ft.Column(
            expand=True,
            controls=[
                header,
                ft.Divider(),
                items_view,
                ft.Divider(),
                note_checkbox,
                ft.Row(
                    controls=[
                        text_field,
                        ft.IconButton(
                            icon=ft.Icons.ADD_CIRCLE,
                            icon_size=34,
                            tooltip="Añadir",
                            on_click=add_item,
                        ),
                    ]
                ),
            ],
        )

        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=4, vertical=12),
            content=ft.Card(
                content=ft.Container(
                    padding=18,
                    content=card_content,
                )
            ),
        )

    def show_edit_list_title_dialog(self, list_id: str) -> None:
        shopping_list = self._find_list(list_id)
        if shopping_list is None:
            return

        title_field = ft.TextField(
            label="Título de la lista",
            value=shopping_list.get("title", ""),
            autofocus=True,
            capitalization=ft.TextCapitalization.SENTENCES,
        )

        def save_title(_: ft.Event[Any]) -> None:
            new_title = (title_field.value or "").strip()
            if not new_title:
                self._show_message("El título no puede quedar vacío.")
                return

            shopping_list["title"] = new_title
            self.storage.save(self.data)
            self.page.pop_dialog()
            self.refresh(selected_list_id=list_id)

        title_field.on_submit = save_title

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Editar título"),
                content=title_field,
                actions=[
                    ft.TextButton(
                        "Cancelar",
                        on_click=lambda e: self.page.pop_dialog(),
                    ),
                    ft.FilledButton("Guardar", on_click=save_title),
                ],
            )
        )

    def show_new_list_dialog(self, _: ft.Event[Any]) -> None:
        suggested_title = f"Compra {datetime.now().strftime('%d/%m/%Y')}"
        title_field = ft.TextField(
            label="Nombre de la lista",
            value=suggested_title,
            autofocus=True,
        )

        def create_list(_: ft.Event[Any]) -> None:
            title = (title_field.value or suggested_title).strip() or suggested_title
            new_list = self._new_list_data(title)
            insertion_index = min(self.current_index + 1, len(self.shopping_lists))
            self.shopping_lists.insert(insertion_index, new_list)
            self.current_index = insertion_index
            self.storage.save(self.data)
            self.page.pop_dialog()
            self.refresh(selected_list_id=new_list["id"])

        title_field.on_submit = create_list

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Nueva lista"),
                content=title_field,
                actions=[
                    ft.TextButton(
                        "Cancelar",
                        on_click=lambda e: self.page.pop_dialog(),
                    ),
                    ft.FilledButton("Crear", on_click=create_list),
                ],
            )
        )

    def show_delete_list_dialog(self, list_id: str) -> None:
        shopping_list = self._find_list(list_id)
        if shopping_list is None:
            return

        def delete_list(_: ft.Event[Any]) -> None:
            self.data["lists"] = [
                saved_list
                for saved_list in self.shopping_lists
                if saved_list["id"] != list_id
            ]
            self.current_index = 0
            self._ensure_first_list()
            self.storage.save(self.data)
            self.page.pop_dialog()
            self.refresh()

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Eliminar lista"),
                content=ft.Text(
                    f"¿Quieres eliminar «{shopping_list['title']}» y todos sus elementos?"
                ),
                actions=[
                    ft.TextButton(
                        "Cancelar",
                        on_click=lambda e: self.page.pop_dialog(),
                    ),
                    ft.FilledButton("Eliminar", on_click=delete_list),
                ],
            )
        )


def main(page: ft.Page) -> None:
    ShoppingListApp(page)


if __name__ == "__main__":
    ft.run(main)
