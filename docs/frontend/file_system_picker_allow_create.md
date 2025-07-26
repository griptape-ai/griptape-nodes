# FileSystemPicker `allow_create` and `allow_rename` Frontend Implementation Guide

## Overview

The `allow_create` and `allow_rename` features allow users to create new files or directories and rename existing ones directly through the FileSystemPicker component.

## Backend Events

### CreateFileRequest
**Purpose**: Request to create a new file or directory

**Payload**:
```typescript
interface CreateFileRequest {
  path: string;                    // Path where file/directory should be created
  is_directory: boolean;           // true = create directory, false = create file
  content?: string;               // Optional initial content for files
  encoding?: string;              // Text encoding (default: "utf-8")
  workspace_only?: boolean;       // Constrain to workspace (default: true)
}
```

### CreateFileResultSuccess
**Purpose**: Successful file/directory creation response

**Payload**:
```typescript
interface CreateFileResultSuccess {
  created_path: string;           // Full path of created file/directory
}
```

### CreateFileResultFailure
**Purpose**: Failed file/directory creation response

**Payload**:
```typescript
interface CreateFileResultFailure {
  error?: string;                 // Optional error message
}
```

### RenameFileRequest
**Purpose**: Request to rename a file or directory

**Payload**:
```typescript
interface RenameFileRequest {
  old_path: string;               // Current path of the file/directory to rename
  new_path: string;               // New path for the file/directory
  workspace_only?: boolean;       // Constrain to workspace (default: true)
}
```

### RenameFileResultSuccess
**Purpose**: Successful file/directory rename response

**Payload**:
```typescript
interface RenameFileResultSuccess {
  old_path: string;               // Original path of the renamed item
  new_path: string;               // New path of the renamed item
}
```

### RenameFileResultFailure
**Purpose**: Failed file/directory rename response

**Payload**:
```typescript
interface RenameFileResultFailure {
  error?: string;                 // Optional error message
}
```

## Frontend Implementation Flow

### 1. UI State Management
```typescript
interface FileSystemPickerState {
  allowCreate: boolean;           // From trait configuration
  allowRename: boolean;           // From trait configuration
  allowFiles: boolean;            // From trait configuration
  allowDirectories: boolean;      // From trait configuration
  currentPath: string;            // Current directory being browsed
  selectedItems: string[];        // Currently selected files/directories
  isCreating: boolean;            // Loading state during creation
  isRenaming: boolean;            // Loading state during rename
}
```

### 2. User Input Detection
```typescript
function handlePathInput(inputPath: string, state: FileSystemPickerState) {
  // Check if user is trying to create something new
  if (state.allowCreate && !pathExists(inputPath)) {
    const isDirectory = inputPath.endsWith('/') || inputPath.endsWith('\\');
    
    // Validate creation permissions
    if (isDirectory && !state.allowDirectories) {
      showError("Directory creation not allowed");
      return;
    }
    
    if (!isDirectory && !state.allowFiles) {
      showError("File creation not allowed");
      return;
    }
    
    // Prompt user for creation
    promptForCreation(inputPath, isDirectory);
  }
}
```

### 3. Creation Prompt UI
```typescript
function promptForCreation(path: string, isDirectory: boolean) {
  const message = isDirectory 
    ? `Directory "${path}" doesn't exist. Create it?`
    : `File "${path}" doesn't exist. Create it?`;
    
  const options = {
    title: "Create New",
    message,
    actions: [
      { label: "Cancel", type: "cancel" },
      { label: "Create", type: "primary" }
    ]
  };
  
  showDialog(options).then(result => {
    if (result === "Create") {
      createFileOrDirectory(path, isDirectory);
    }
  });
}
```

### 4. Backend Communication
```typescript
async function createFileOrDirectory(path: string, isDirectory: boolean) {
  setState({ isCreating: true });
  
  try {
    const request: CreateFileRequest = {
      path,
      is_directory: isDirectory,
      content: isDirectory ? undefined : "", // Empty file content
      encoding: "utf-8",
      workspace_only: true
    };
    
    const response = await sendEvent("CreateFileRequest", request);
    
    if (response.type === "CreateFileResultSuccess") {
      // Refresh directory listing to show new item
      await refreshDirectoryListing();
      showSuccess(`Created ${isDirectory ? 'directory' : 'file'}: ${path}`);
    } else {
      showError(`Failed to create ${isDirectory ? 'directory' : 'file'}: ${response.error || 'Unknown error'}`);
    }
  } catch (error) {
    showError(`Creation failed: ${error.message}`);
  } finally {
    setState({ isCreating: false });
  }
}
```

### 5. Enhanced File Input Handling
```typescript
function handleFileInput(input: string) {
  // Normal file selection logic
  if (pathExists(input)) {
    selectFile(input);
    return;
  }
  
  // Creation logic
  if (allowCreate) {
    const isDirectory = input.endsWith('/') || input.endsWith('\\');
    
    // Determine if user wants to create file or directory
    if (allowFiles && allowDirectories) {
      // Show choice dialog
      showFileOrDirectoryChoice(input);
    } else if (allowFiles && !allowDirectories) {
      // Force file creation
      promptForCreation(input, false);
    } else if (allowDirectories && !allowFiles) {
      // Force directory creation
      promptForCreation(input, true);
    }
  } else {
    showError("File or directory does not exist");
  }
}
```

### 6. File vs Directory Choice Dialog
```typescript
function showFileOrDirectoryChoice(path: string) {
  const baseName = path.replace(/[/\\]$/, ''); // Remove trailing slash
  
  showDialog({
    title: "Create New",
    message: `"${baseName}" doesn't exist. What would you like to create?`,
    actions: [
      { label: "Cancel", type: "cancel" },
      { label: "File", type: "default" },
      { label: "Directory", type: "default" }
    ]
  }).then(result => {
    switch (result) {
      case "File":
        createFileOrDirectory(baseName, false);
        break;
      case "Directory":
        createFileOrDirectory(baseName, true);
        break;
    }
  });
}
```

### 7. Rename Functionality
```typescript
function handleRenameRequest(oldPath: string, newPath: string) {
  if (!state.allowRename) {
    showError("Rename functionality not enabled");
    return;
  }
  
  // Validate that the item exists
  if (!pathExists(oldPath)) {
    showError("Item to rename does not exist");
    return;
  }
  
  // Validate that new path doesn't exist
  if (pathExists(newPath)) {
    showError("Destination path already exists");
    return;
  }
  
  // Prompt for confirmation
  promptForRename(oldPath, newPath);
}

function promptForRename(oldPath: string, newPath: string) {
  const oldName = getFileName(oldPath);
  const newName = getFileName(newPath);
  
  showDialog({
    title: "Rename Item",
    message: `Rename "${oldName}" to "${newName}"?`,
    actions: [
      { label: "Cancel", type: "cancel" },
      { label: "Rename", type: "primary" }
    ]
  }).then(result => {
    if (result === "Rename") {
      renameFileOrDirectory(oldPath, newPath);
    }
  });
}

async function renameFileOrDirectory(oldPath: string, newPath: string) {
  setState({ isRenaming: true });
  
  try {
    const request: RenameFileRequest = {
      old_path: oldPath,
      new_path: newPath,
      workspace_only: true
    };
    
    const response = await sendEvent("RenameFileRequest", request);
    
    if (response.type === "RenameFileResultSuccess") {
      // Refresh directory listing to show renamed item
      await refreshDirectoryListing();
      showSuccess(`Renamed: ${getFileName(oldPath)} → ${getFileName(newPath)}`);
    } else {
      showError(`Failed to rename: ${response.error || 'Unknown error'}`);
    }
  } catch (error) {
    showError(`Rename failed: ${error.message}`);
  } finally {
    setState({ isRenaming: false });
  }
}
```

### 8. Context Menu Integration
```typescript
function showContextMenu(item: FileSystemEntry, position: { x: number, y: number }) {
  const menuItems = [];
  
  if (state.allowRename) {
    menuItems.push({
      label: "Rename",
      icon: "edit",
      action: () => showRenameDialog(item)
    });
  }
  
  if (state.allowCreate) {
    menuItems.push({
      label: "Create New",
      icon: "plus",
      action: () => showCreateDialog(item.path)
    });
  }
  
  showContextMenu(menuItems, position);
}

function showRenameDialog(item: FileSystemEntry) {
  const currentName = item.name;
  
  showInputDialog({
    title: "Rename Item",
    message: "Enter new name:",
    defaultValue: currentName,
    validation: (value) => {
      if (!value.trim()) return "Name cannot be empty";
      if (value.includes('/') || value.includes('\\')) return "Name cannot contain path separators";
      return null;
    }
  }).then(newName => {
    if (newName && newName !== currentName) {
      const newPath = getParentPath(item.path) + '/' + newName;
      renameFileOrDirectory(item.path, newPath);
    }
  });
}
```

## UI/UX Considerations

### 1. Visual Indicators
- Show a "Create" button or icon when `allowCreate` is true
- Use different icons for file vs directory creation
- Show loading spinner during creation process

### 2. Error Handling
- Display specific error messages from backend
- Handle permission errors gracefully
- Provide helpful suggestions for common issues

### 3. Validation
- Prevent creation of files with invalid names
- Check for reserved characters in file/directory names
- Validate path length limits

### 4. Accessibility
- Provide keyboard shortcuts for creation actions
- Include proper ARIA labels for screen readers
- Ensure focus management during dialogs

## Example Usage Scenarios

### Scenario 1: Creating a Directory
```
User types: "new_project/"
System detects: Directory doesn't exist, allowCreate=true, allowDirectories=true
Action: Shows creation prompt → Creates directory → Refreshes listing
```

### Scenario 2: Creating a File
```
User types: "config.json"
System detects: File doesn't exist, allowCreate=true, allowFiles=true
Action: Shows creation prompt → Creates empty file → Refreshes listing
```

### Scenario 3: Ambiguous Input
```
User types: "data"
System detects: Doesn't exist, allowCreate=true, allowFiles=true, allowDirectories=true
Action: Shows choice dialog → User selects file/directory → Creates item
```

### Scenario 4: Renaming a File
```
User right-clicks: "old_name.txt"
System detects: allowRename=true, allowFiles=true
Action: Shows rename dialog → User enters "new_name.txt" → Renames file → Refreshes listing
```

### Scenario 5: Renaming a Directory
```
User right-clicks: "old_folder"
System detects: allowRename=true, allowDirectories=true
Action: Shows rename dialog → User enters "new_folder" → Renames directory → Refreshes listing
```

## Integration with Existing Components

The `allow_create` functionality should integrate seamlessly with existing FileSystemPicker features:

- **Multiple selection**: Creation should work with single and multiple selection modes
- **File filters**: Respect existing file type and extension filters
- **Workspace constraints**: Honor workspace-only settings
- **Initial path**: Work correctly with initial path configurations

## Backend Integration Notes

The backend implementation includes:

1. **New Events**: 
   - `CreateFileRequest`, `CreateFileResultSuccess`, `CreateFileResultFailure`
   - `RenameFileRequest`, `RenameFileResultSuccess`, `RenameFileResultFailure`
2. **OS Manager Handlers**: 
   - `on_create_file_request()` method in `OSManager`
   - `on_rename_file_request()` method in `OSManager`
3. **Validation**: Workspace constraints, path validation, existence checks
4. **Error Handling**: Comprehensive error messages and logging

The trait configuration passes `allowCreate` and `allowRename` in the UI options, which the frontend should use to enable/disable the respective functionalities.

This implementation provides a smooth user experience for creating files and directories directly through the file picker interface! 🚀 