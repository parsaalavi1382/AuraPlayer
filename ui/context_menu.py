from PyQt6.QtWidgets import QMenu
from PyQt6.QtGui import QAction

def build_track_context_menu(
    parent, 
    track, 
    store, 
    engine=None, 
    on_play=None, 
    on_remove=None, 
    remove_text="Remove Song",
    on_edit=None,
    on_properties=None
) -> QMenu:
    menu = QMenu(parent)
    from ui.theme import THEMES, DEFAULT_THEME
    theme_key = store.cache.settings.theme
    theme = THEMES.get(theme_key, THEMES[DEFAULT_THEME])
    bg = theme.get("surface", "#1E222B")
    text = theme.get("text_primary", "#FFFFFF")
    border = theme.get("border", "#2E323C")
    accent = theme.get("accent", "#6C5CE7")

    qss = f"""
        QMenu {{
            background-color: {bg};
            color: {text};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 4px;
        }}
        QMenu::item {{
            padding: 6px 12px;
            border-radius: 4px;
            color: {text};
        }}
        QMenu::item:selected {{
            background-color: {accent};
            color: {text};
        }}
    """
    menu.setStyleSheet(qss)

    if engine:
        add_queue_act = QAction("Add to Queue", parent)
        add_queue_act.triggered.connect(lambda: engine.add_to_queue(track.path))
        menu.addAction(add_queue_act)
        
        play_next_act = QAction("Play Next", parent)
        play_next_act.triggered.connect(lambda: engine.play_next(track.path))
        menu.addAction(play_next_act)
        
        menu.addSeparator()

    if not on_edit:
        def default_edit():
            from ui.widgets.metadata_editor_dialog import MetadataEditorDialog
            dialog = MetadataEditorDialog(track, store, parent)
            dialog.exec()
        on_edit = default_edit

    if on_edit:
        edit_act = QAction("Edit Metadata", parent)
        edit_act.triggered.connect(on_edit)
        menu.addAction(edit_act)

    if on_remove:
        remove_act = QAction(remove_text, parent)
        remove_act.triggered.connect(on_remove)
        menu.addAction(remove_act)

    menu.addSeparator()

    add_playlist_menu = QMenu("Add to Playlist", parent)
    add_playlist_menu.setStyleSheet(qss)
    custom_playlists = [p for p in store.all_playlists() if not p.id.startswith("smart_")]
    
    fav_action = QAction("Favorites", parent)
    fav_action.triggered.connect(lambda: store.add_tracks_to_playlist("smart_favorites", [track.path]))
    add_playlist_menu.addAction(fav_action)
    
    if custom_playlists:
        add_playlist_menu.addSeparator()
        for pl in custom_playlists:
            pl_action = QAction(pl.name, parent)
            pl_action.triggered.connect(lambda checked, p_id=pl.id, t_path=track.path: store.add_tracks_to_playlist(p_id, [t_path]))
            add_playlist_menu.addAction(pl_action)
            
    menu.addMenu(add_playlist_menu)

    if not on_properties:
        def default_properties():
            from ui.widgets.properties_dialog import PropertiesDialog
            dialog = PropertiesDialog(track, store, parent)
            dialog.exec()
        on_properties = default_properties

    if on_properties:
        menu.addSeparator()
        prop_act = QAction("Properties", parent)
        prop_act.triggered.connect(on_properties)
        menu.addAction(prop_act)

    return menu
