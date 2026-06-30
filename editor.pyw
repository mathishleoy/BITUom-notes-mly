#!/usr/bin/env python3
"""
BIT Notes Structure Editor - Complete
Features: load/save, tree with expand/collapse (state preserved),
add folder/file (auto-name), bulk add, edit, delete, move (drag-drop & buttons),
move up/down, preview, save, and selection is preserved after changes.
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, scrolledtext
import re
import ast
import json
import urllib.request
import urllib.error
import os


class StructureEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("BIT Notes Structure Editor")
        self.filepath = "index.html"

        if not os.path.isfile(self.filepath):
            answer = messagebox.askyesno(
                "File not found",
                f"'{self.filepath}' not found.\nSelect a different file?"
            )
            if answer:
                from tkinter import filedialog
                self.filepath = filedialog.askopenfilename(
                    title="Select index.html",
                    filetypes=[("HTML files", "*.html"), ("All files", "*.*")]
                )
                if not self.filepath:
                    messagebox.showerror("Error", "No file selected. Exiting.")
                    root.destroy()
                    return
            else:
                root.destroy()
                return

        try:
            self.load_file()
        except Exception as e:
            messagebox.showerror("Loading Error", str(e))
            root.destroy()
            return

        self.create_widgets()
        self.populate_trees()
        self.setup_drag_drop()

    def load_file(self):
        with open(self.filepath, 'r', encoding='utf-8') as f:
            self.html_content = f.read()

        self.folder_data = self.extract_and_parse("FOLDER_STRUCTURE")
        self.papers_data = self.extract_and_parse("PAPERS_STRUCTURE")

    def extract_and_parse(self, var_name):
        pattern = rf'(const|let|var)\s+{var_name}\s*=\s*'
        match = re.search(pattern, self.html_content, re.DOTALL)
        if not match:
            raise ValueError(f"Could not find '{var_name}' assignment.")

        start = match.end()
        brace_count = 0
        in_string = False
        escape = False
        for i, ch in enumerate(self.html_content[start:], start):
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if ch == '"' and not in_string:
                in_string = True
                continue
            if ch == '"' and in_string:
                in_string = False
                continue
            if in_string:
                continue
            if ch == '{':
                brace_count += 1
            elif ch == '}':
                brace_count -= 1
                if brace_count == 0:
                    end = i + 1
                    break
        else:
            raise ValueError(f"Could not find closing brace for '{var_name}'.")

        obj_text = self.html_content[start:end]
        return self.parse_js_object(obj_text)

    def parse_js_object(self, text):
        text = re.sub(r'(?<!")\b(\w+)\b\s*:', r'"\1":', text)
        text = re.sub(r',\s*(?=[}\]])', '', text)
        try:
            return ast.literal_eval(text)
        except Exception as e:
            raise ValueError(f"Failed to parse JS object:\n{e}\nText:\n{text}")

    def create_widgets(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True)

        self.notes_frame = ttk.Frame(notebook)
        self.papers_frame = ttk.Frame(notebook)
        notebook.add(self.notes_frame, text="Notes")
        notebook.add(self.papers_frame, text="Papers")

        self.notes_tree = self.create_tree_view(self.notes_frame, "notes")
        self.papers_tree = self.create_tree_view(self.papers_frame, "papers")

        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=10)

        ttk.Button(btn_frame, text="Preview Changes", command=self.preview_changes).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Save Changes", command=self.save_changes).pack(side='left', padx=5)

    def create_tree_view(self, parent, key):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True, padx=10, pady=10)

        tree = ttk.Treeview(frame, columns=('type', 'url'), show='tree headings')
        tree.heading('#0', text='Name')
        tree.heading('type', text='Type')
        tree.heading('url', text='URL')
        tree.column('#0', width=200)
        tree.column('type', width=100)
        tree.column('url', width=300)
        tree.pack(fill='both', expand=True)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill='x', pady=5)

        ttk.Button(btn_frame, text="Add Folder",
                   command=lambda: self.add_item(tree, key, 'folder')).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="Add File",
                   command=lambda: self.add_item(tree, key, 'file')).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="Add Bulk Files",
                   command=lambda: self.add_bulk_files(tree, key)).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="Edit",
                   command=lambda: self.edit_item(tree, key)).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="Delete",
                   command=lambda: self.delete_item(tree, key)).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="Move Up",
                   command=lambda: self.move_up(tree, key)).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="Move Down",
                   command=lambda: self.move_down(tree, key)).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="Move (to folder)",
                   command=lambda: self.move_item(tree, key)).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="Expand All",
                   command=lambda: self.expand_all(tree)).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="Collapse All",
                   command=lambda: self.collapse_all(tree)).pack(side='left', padx=2)

        tree.data_map = {}
        tree.drag_source = None
        tree.key = key
        return tree

    # ---- Helper: get iid for a node ----
    def get_iid_for_node(self, tree, node):
        for iid, data_node in tree.data_map.items():
            if data_node is node:
                return iid
        return None

    # ---- Drag-and-Drop ----
    def setup_drag_drop(self):
        for tree in (self.notes_tree, self.papers_tree):
            tree.bind('<Button-1>', self.on_drag_start)
            tree.bind('<B1-Motion>', self.on_drag_motion)
            tree.bind('<ButtonRelease-1>', self.on_drag_release)

    def on_drag_start(self, event):
        tree = event.widget
        iid = tree.identify_row(event.y)
        if iid and iid in tree.data_map:
            tree.drag_source = iid
        else:
            tree.drag_source = None

    def on_drag_motion(self, event):
        pass

    def on_drag_release(self, event):
        tree = event.widget
        if not tree.drag_source:
            return
        source_iid = tree.drag_source
        source_node = tree.data_map.get(source_iid)
        if not source_node:
            return

        target_iid = tree.identify_row(event.y)
        if target_iid == source_iid:
            tree.drag_source = None
            return

        if not target_iid:
            parent_node = self.folder_data if tree.key == 'notes' else self.papers_data
            insert_after = None
        else:
            target_node = tree.data_map.get(target_iid)
            if not target_node:
                tree.drag_source = None
                return
            if target_node['type'] == 'folder':
                parent_node = target_node
                insert_after = None
            else:
                parent_iid = tree.parent(target_iid)
                if parent_iid:
                    parent_node = tree.data_map.get(parent_iid)
                else:
                    parent_node = self.folder_data if tree.key == 'notes' else self.papers_data
                insert_after = target_node

        if source_node is parent_node:
            tree.drag_source = None
            return
        if source_node['type'] == 'folder' and self.is_descendant(source_node, parent_node):
            messagebox.showerror("Error", "Cannot move a folder into itself or its child.")
            tree.drag_source = None
            return
        if self.is_root(source_node):
            messagebox.showerror("Error", "Cannot move the root folder.")
            tree.drag_source = None
            return

        source_parent = self.find_parent(tree, source_iid, tree.key)
        if source_parent is None:
            tree.drag_source = None
            return
        source_parent['children'].remove(source_node)

        if insert_after is None:
            parent_node.setdefault('children', []).append(source_node)
        else:
            idx = parent_node['children'].index(insert_after) + 1
            parent_node['children'].insert(idx, source_node)

        self.refresh_tree(tree, tree.key, select_node=source_node)
        tree.drag_source = None

    # ---- Expand / Collapse ----
    def expand_all(self, tree):
        def expand_children(parent):
            for child in tree.get_children(parent):
                tree.item(child, open=True)
                expand_children(child)
        expand_children('')

    def collapse_all(self, tree):
        def collapse_children(parent):
            for child in tree.get_children(parent):
                tree.item(child, open=False)
                collapse_children(child)
        collapse_children('')

    # ---- Populate trees ----
    def populate_trees(self):
        self.populate_tree(self.notes_tree, self.folder_data, 'notes')
        self.populate_tree(self.papers_tree, self.papers_data, 'papers')

    def populate_tree(self, tree, data_node, key, parent=''):
        root_id = tree.insert(parent, 'end', text=data_node['name'],
                              values=('folder', ''))
        tree.data_map[root_id] = data_node
        self.populate_children(tree, data_node, root_id)

    def populate_children(self, tree, parent_node, parent_iid):
        for child in parent_node.get('children', []):
            if child['type'] == 'folder':
                values = ('folder', '')
            else:
                values = ('file', child.get('url', ''))
            iid = tree.insert(parent_iid, 'end', text=child['name'], values=values)
            tree.data_map[iid] = child
            if child['type'] == 'folder':
                self.populate_children(tree, child, iid)

    # ---- Item helpers ----
    def get_selected_node(self, tree):
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("No selection", "Please select an item.")
            return None, None
        iid = selected[0]
        node = tree.data_map.get(iid)
        if not node:
            messagebox.showerror("Error", "Selected item not found.")
            return None, None
        return iid, node

    def is_root(self, node):
        return node is self.folder_data or node is self.papers_data

    def find_parent(self, tree, iid, key):
        parent_iid = tree.parent(iid)
        if parent_iid == '':
            return self.folder_data if key == 'notes' else self.papers_data
        return tree.data_map.get(parent_iid)

    def is_descendant(self, ancestor, node):
        if node is ancestor:
            return True
        for child in ancestor.get('children', []):
            if child['type'] == 'folder':
                if self.is_descendant(child, node):
                    return True
        return False

    # ---- refresh_tree with selection ----
    def refresh_tree(self, tree, key, select_node=None):
        # Store open state using the node's object id (stable)
        open_ids = set()
        def collect_open(parent):
            for child in tree.get_children(parent):
                if tree.item(child, 'open'):
                    node = tree.data_map.get(child)
                    if node:
                        open_ids.add(id(node))
                collect_open(child)
        collect_open('')

        tree.delete(*tree.get_children())
        tree.data_map.clear()
        data = self.folder_data if key == 'notes' else self.papers_data
        self.populate_tree(tree, data, key)

        # Restore open state
        def restore_open(parent):
            for child in tree.get_children(parent):
                node = tree.data_map.get(child)
                if node and id(node) in open_ids:
                    tree.item(child, open=True)
                restore_open(child)
        restore_open('')

        # Restore selection
        if select_node:
            iid = self.get_iid_for_node(tree, select_node)
            if iid:
                tree.selection_set(iid)
                tree.see(iid)

    # ---- Add folder/file ----
    def add_item(self, tree, key, item_type):
        selected = tree.selection()
        if selected:
            parent_iid = selected[0]
            parent_node = tree.data_map.get(parent_iid)
            if parent_node['type'] != 'folder':
                messagebox.showerror("Error", "Cannot add to a file. Select a folder.")
                return
        else:
            parent_node = self.folder_data if key == 'notes' else self.papers_data

        if item_type == 'folder':
            name = simpledialog.askstring("Add Folder", "Enter folder name:", parent=self.root)
            if not name:
                return
            new_node = {"type": "folder", "name": name.strip(), "children": []}
        else:
            url = simpledialog.askstring("Add File", "Enter Google Drive URL:", parent=self.root)
            if not url:
                return
            url = url.strip()
            if not self.validate_url(url):
                messagebox.showerror("Invalid URL", "URL must be a Google Drive share link.")
                return
            if not self.check_url_access(url):
                if not messagebox.askyesno("URL not accessible",
                                           "The URL seems inaccessible. Continue anyway?"):
                    return
            auto_name = self.fetch_file_name_from_drive(url)
            if auto_name:
                auto_name = re.sub(r'\s*[-–]\s*Google Drive$', '', auto_name).strip()
            name = simpledialog.askstring("Add File", "Enter file name:",
                                          parent=self.root,
                                          initialvalue=auto_name if auto_name else "")
            if name is None:
                return
            name = name.strip()
            if not name:
                messagebox.showerror("Error", "File name cannot be empty.")
                return
            new_node = {"type": "file", "name": name, "url": url}

        parent_node.setdefault('children', []).append(new_node)
        self.refresh_tree(tree, key, select_node=new_node)

    # ---- Bulk add ----
    def add_bulk_files(self, tree, key):
        selected = tree.selection()
        if selected:
            parent_iid = selected[0]
            parent_node = tree.data_map.get(parent_iid)
            if parent_node['type'] != 'folder':
                messagebox.showerror("Error", "Cannot add to a file. Select a folder.")
                return
        else:
            parent_node = self.folder_data if key == 'notes' else self.papers_data

        dialog = tk.Toplevel(self.root)
        dialog.title("Add Bulk Files")
        dialog.geometry("500x400")
        tk.Label(dialog, text="Enter one Google Drive URL per line:").pack(pady=5)
        text_widget = scrolledtext.ScrolledText(dialog, wrap='none', font=('Courier', 10))
        text_widget.pack(fill='both', expand=True, padx=10, pady=10)

        def on_ok():
            content = text_widget.get('1.0', tk.END).strip()
            if not content:
                messagebox.showwarning("Empty", "No URLs entered.")
                return
            urls = [u.strip() for u in content.splitlines() if u.strip()]
            added = 0
            last_added = None
            for url in urls:
                if not self.validate_url(url):
                    messagebox.showerror("Invalid URL", f"Invalid Drive URL:\n{url}")
                    continue
                if not self.check_url_access(url):
                    if not messagebox.askyesno("URL not accessible",
                                               f"The URL seems inaccessible:\n{url}\nContinue anyway?"):
                        continue
                auto_name = self.fetch_file_name_from_drive(url)
                if auto_name:
                    auto_name = re.sub(r'\s*[-–]\s*Google Drive$', '', auto_name).strip()
                else:
                    m = re.search(r'/d/([a-zA-Z0-9_-]+)', url)
                    auto_name = m.group(1) if m else "unknown"
                if not auto_name:
                    auto_name = "unnamed"
                new_node = {"type": "file", "name": auto_name, "url": url}
                parent_node.setdefault('children', []).append(new_node)
                added += 1
                last_added = new_node
            if added > 0:
                self.refresh_tree(tree, key, select_node=last_added)
                messagebox.showinfo("Bulk Add", f"Added {added} file(s).")
            else:
                messagebox.showwarning("No files", "No valid files were added.")
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Add All", command=on_ok).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Cancel", command=on_cancel).pack(side='left', padx=5)

        dialog.transient(self.root)
        dialog.grab_set()
        self.root.wait_window(dialog)

    # ---- Fetch file name from Drive ----
    def fetch_file_name_from_drive(self, url):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                html = resp.read().decode('utf-8')
                match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
                if match:
                    title = match.group(1).strip()
                    return title if title else None
        except Exception:
            pass
        return None

    # ---- URL validation ----
    def validate_url(self, url):
        pattern = r'^https://drive\.google\.com/file/d/[a-zA-Z0-9_-]+/view\?usp=(sharing|drive_link)$'
        return re.match(pattern, url) is not None

    def check_url_access(self, url):
        try:
            req = urllib.request.Request(url, method='HEAD')
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    # ---- Edit ----
    def edit_item(self, tree, key):
        iid, node = self.get_selected_node(tree)
        if not node:
            return
        if self.is_root(node):
            messagebox.showinfo("Info", "Cannot edit the root folder.")
            return

        if node['type'] == 'folder':
            new_name = simpledialog.askstring("Rename Folder", "Enter new name:",
                                              initialvalue=node['name'])
            if new_name is not None and new_name.strip():
                node['name'] = new_name.strip()
                tree.item(iid, text=new_name.strip())
                # no refresh needed, selection stays
        else:
            new_name = simpledialog.askstring("Rename File", "Enter new name:",
                                              initialvalue=node['name'])
            if new_name is not None and new_name.strip():
                node['name'] = new_name.strip()
                tree.item(iid, text=new_name.strip())

            new_url = simpledialog.askstring("Update URL", "Enter new URL:",
                                             initialvalue=node.get('url', ''))
            if new_url is not None:
                new_url = new_url.strip()
                if new_url:
                    if not self.validate_url(new_url):
                        messagebox.showerror("Invalid URL", "URL must be a Google Drive share link.")
                        return
                    if not self.check_url_access(new_url):
                        if not messagebox.askyesno("URL not accessible",
                                                   "The URL seems inaccessible. Continue anyway?"):
                            return
                    node['url'] = new_url
                    tree.set(iid, 'url', new_url)

    # ---- Delete ----
    def delete_item(self, tree, key):
        iid, node = self.get_selected_node(tree)
        if not node:
            return
        if self.is_root(node):
            messagebox.showinfo("Info", "Cannot delete the root folder.")
            return

        if not messagebox.askyesno("Delete", f"Delete '{node['name']}'?"):
            return

        parent = self.find_parent(tree, iid, key)
        if parent is None:
            messagebox.showerror("Error", "Could not find parent.")
            return
        # Find sibling to select after deletion
        children = parent['children']
        idx = children.index(node)
        select_after = None
        if len(children) > 1:
            if idx + 1 < len(children):
                select_after = children[idx + 1]
            else:
                select_after = children[idx - 1]
        else:
            select_after = parent  # select parent if no siblings

        parent['children'].remove(node)
        self.refresh_tree(tree, key, select_node=select_after)

    # ---- Move Up / Down ----
    def move_up(self, tree, key):
        iid, node = self.get_selected_node(tree)
        if not node:
            return
        if self.is_root(node):
            return
        parent = self.find_parent(tree, iid, key)
        if parent is None:
            return
        children = parent['children']
        idx = children.index(node)
        if idx == 0:
            return
        children[idx], children[idx-1] = children[idx-1], children[idx]
        self.refresh_tree(tree, key, select_node=node)

    def move_down(self, tree, key):
        iid, node = self.get_selected_node(tree)
        if not node:
            return
        if self.is_root(node):
            return
        parent = self.find_parent(tree, iid, key)
        if parent is None:
            return
        children = parent['children']
        idx = children.index(node)
        if idx == len(children) - 1:
            return
        children[idx], children[idx+1] = children[idx+1], children[idx]
        self.refresh_tree(tree, key, select_node=node)

    # ---- Move to folder ----
    def move_item(self, tree, key):
        iid, node = self.get_selected_node(tree)
        if not node:
            return
        if self.is_root(node):
            messagebox.showinfo("Info", "Cannot move the root folder.")
            return

        dest = self.select_destination(tree, key)
        if dest is None:
            return
        if dest is node:
            return
        if node['type'] == 'folder':
            if self.is_descendant(node, dest):
                messagebox.showerror("Error", "Cannot move a folder into itself or its child.")
                return

        parent = self.find_parent(tree, iid, key)
        if parent is None:
            return
        parent['children'].remove(node)
        dest.setdefault('children', []).append(node)
        self.refresh_tree(tree, key, select_node=node)

    def select_destination(self, tree, key):
        dialog = tk.Toplevel(self.root)
        dialog.title("Select Destination Folder")
        dialog.geometry("300x400")
        dest_tree = ttk.Treeview(dialog, show='tree')
        dest_tree.pack(fill='both', expand=True, padx=10, pady=10)

        def populate_dest(node, parent=''):
            if node['type'] == 'folder':
                iid = dest_tree.insert(parent, 'end', text=node['name'])
                dest_tree.data_map[iid] = node
                for child in node.get('children', []):
                    if child['type'] == 'folder':
                        populate_dest(child, iid)

        dest_tree.data_map = {}
        root_node = self.folder_data if key == 'notes' else self.papers_data
        populate_dest(root_node)

        selected_iid = None

        def on_select():
            nonlocal selected_iid
            sel = dest_tree.selection()
            if not sel:
                messagebox.showwarning("No selection", "Please select a folder.")
                return
            selected_iid = sel[0]
            dialog.destroy()

        btn = ttk.Button(dialog, text="Select", command=on_select)
        btn.pack(pady=5)

        dialog.transient(self.root)
        dialog.grab_set()
        self.root.wait_window(dialog)

        if selected_iid is None:
            return None
        return dest_tree.data_map[selected_iid]

    # ---- Save / preview ----
    def generate_new_content(self):
        try:
            folder_js = json.dumps(self.folder_data, indent=2, ensure_ascii=False)
            papers_js = json.dumps(self.papers_data, indent=2, ensure_ascii=False)
        except Exception as e:
            return None, False, f"JSON serialization failed: {e}"

        content = self.html_content
        try:
            content = self.replace_structure(content, "FOLDER_STRUCTURE", folder_js)
            content = self.replace_structure(content, "PAPERS_STRUCTURE", papers_js)
            return content, True, None
        except Exception as e:
            return None, False, str(e)

    def replace_structure(self, content, var_name, new_obj_str):
        pattern = rf'(const|let|var)\s+{var_name}\s*=\s*'
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            raise ValueError(f"Could not find '{var_name}' assignment.")

        keyword = match.group(1)
        start = match.start()
        brace_start = match.end()

        brace_count = 0
        in_string = False
        escape = False
        for i, ch in enumerate(content[brace_start:], brace_start):
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if ch == '"' and not in_string:
                in_string = True
                continue
            if ch == '"' and in_string:
                in_string = False
                continue
            if in_string:
                continue
            if ch == '{':
                brace_count += 1
            elif ch == '}':
                brace_count -= 1
                if brace_count == 0:
                    end = i + 1
                    break
        else:
            raise ValueError(f"Could not find closing brace for '{var_name}'.")

        rest = content[end:]
        semicolon = ''
        m = re.match(r'\s*;', rest)
        if m:
            semicolon = ';'
            end += m.end()

        new_assignment = f'{keyword} {var_name} = {new_obj_str}{semicolon}'
        return content[:start] + new_assignment + content[end:]

    def preview_changes(self):
        new_content, ok, err = self.generate_new_content()
        if not ok:
            messagebox.showerror("Preview Error", err)
            return
        win = tk.Toplevel(self.root)
        win.title("Preview of modified index.html")
        win.geometry("800x600")
        text = scrolledtext.ScrolledText(win, wrap='none', font=('Courier', 10))
        text.pack(fill='both', expand=True)
        text.insert('1.0', new_content)
        text.config(state='disabled')

    def save_changes(self):
        new_content, ok, err = self.generate_new_content()
        if not ok:
            messagebox.showerror("Save Error", err)
            return

        temp_file = self.filepath + ".tmp"
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(new_content)
            os.replace(temp_file, self.filepath)
            messagebox.showinfo("Success", "Changes saved successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to write file:\n{e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)


def main():
    root = tk.Tk()
    app = StructureEditor(root)
    root.mainloop()


if __name__ == "__main__":
    main()