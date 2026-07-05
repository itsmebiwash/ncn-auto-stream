Set WshShell = CreateObject("WScript.Shell")
' Get the directory of this script
strPath = Wscript.ScriptFullName
Set objFSO = CreateObject("Scripting.FileSystemObject")
strFolder = objFSO.GetParentFolderName(strPath)

' Run the bat file hidden (0)
WshShell.Run chr(34) & strFolder & "\run_sync.bat" & Chr(34), 0
Set WshShell = Nothing
