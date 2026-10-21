; Ali - Windows o'rnatuvchisi (Inno Setup 6). Yig'ish: installer\build_windows.ps1
; O'rnatishda: maxfiylik siyosati -> ism -> ruxsatlar (har biri alohida) -> AI kalitlari (ixtiyoriy).
; Natija %LOCALAPPDATA%\Ali\.env ga yoziladi; Ali birinchi ishga tushganda ruxsatlarni qo'llaydi.

#define AppVersion "1.0.0"

[Setup]
AppId={{8B5C2A6E-4D1F-4E7A-9C3B-2F6A1D0E9B71}
AppName=Ali
AppVersion={#AppVersion}
AppPublisher=Ali
DefaultDirName={autopf}\Ali
DefaultGroupName=Ali
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=Ali-Setup-{#AppVersion}
SetupIconFile=ali.ico
UninstallDisplayIcon={app}\Ali.exe
LicenseFile=maxfiylik.txt
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Ish stolida belgi yaratish"
Name: "autostart"; Description: "Kompyuter yoqilganda Ali avtomatik ishga tushsin"

[Files]
Source: "..\dist\Ali\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Ali"; Filename: "{app}\Ali.exe"
Name: "{autodesktop}\Ali"; Filename: "{app}\Ali.exe"; Tasks: desktopicon
Name: "{userstartup}\Ali"; Filename: "{app}\Ali.exe"; Parameters: "--no-browser"; Tasks: autostart

[Run]
Filename: "{app}\Ali.exe"; Description: "Ali'ni hozir ishga tushirish"; Flags: nowait postinstall skipifsilent

[Code]
var
  NamePage: TInputQueryWizardPage;
  PermPage: TInputOptionWizardPage;
  KeyPage: TInputQueryWizardPage;

const
  GroupCount = 8;

function GroupKey(I: Integer): String;
begin
  case I of
    0: Result := 'pc';
    1: Result := 'screen';
    2: Result := 'apps';
    3: Result := 'files';
    4: Result := 'photoshop';
    5: Result := 'coreldraw';
    6: Result := 'ai';
    7: Result := 'online';
  end;
end;

procedure InitializeWizard;
var
  I: Integer;
begin
  NamePage := CreateInputQueryPage(wpLicense, 'Tanishamiz',
    'Ali sizga qanday murojaat qilsin?', 'Ismingizni kiriting. Ali sizni shu ism bilan chaqiradi.');
  NamePage.Add('Ism:', False);
  NamePage.Values[0] := GetUserNameString;

  PermPage := CreateInputOptionPage(NamePage.ID, 'Ruxsatlar',
    'Ali kompyuteringizda nimalarni qila olsin?',
    'Har birini alohida belgilang. Belgilanmaganlari taqiqlanadi. Keyin Ali panelidagi "Ruxsatlar" bo''limida ' +
    'o''zgartirishingiz mumkin. Buyruq bajarish kabi xavfli amallar uchun Ali har safar baribir tasdiq so''raydi.',
    False, False);
  PermPage.Add('Kompyuterni boshqarish: PowerShell buyruqlari, dastur kodlari bilan ishlash');
  PermPage.Add('Ekranni ko''rish (skrinshot)');
  PermPage.Add('Dasturlar va saytlarni ochish');
  PermPage.Add('Fayllar va loyihalarni o''qish');
  PermPage.Add('Adobe Photoshop''da ishlash');
  PermPage.Add('CorelDRAW''da ishlash');
  PermPage.Add('Gemini va ChatGPT''ga savol yuborish');
  PermPage.Add('GitHub, Vercel, Instagram akkauntlari');
  for I := 0 to GroupCount - 1 do
    PermPage.Values[I] := True;

  KeyPage := CreateInputQueryPage(PermPage.ID, 'AI kalitlari',
    'Ali qaysi AI xizmati orqali javob beradi? (ixtiyoriy)',
    'Kamida bitta kalit kerak. Gemini kaliti bepul: aistudio.google.com/apikey. Bo''sh qoldirsangiz, ' +
    'keyin Ali panelidagi "Ulanishlar" bo''limida kiritasiz. Kalitlar faqat shu kompyuterda saqlanadi.');
  KeyPage.Add('Anthropic (Claude) API kaliti:', True);
  KeyPage.Add('Google Gemini API kaliti:', True);
  KeyPage.Add('OpenAI (ChatGPT) API kaliti:', True);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = NamePage.ID) and (Trim(NamePage.Values[0]) = '') then
  begin
    MsgBox('Iltimos, ismingizni kiriting.', mbError, MB_OK);
    Result := False;
  end;
end;

procedure AddLine(var Lines: TArrayOfString; S: String);
begin
  SetArrayLength(Lines, GetArrayLength(Lines) + 1);
  Lines[GetArrayLength(Lines) - 1] := S;
end;

function IsManaged(Line: String): Boolean;
begin
  Result := (Pos('USER_NAME=', Line) = 1) or (Pos('ALI_INSTALL_GROUPS=', Line) = 1) or
    (Pos('PLUGINS_OPEN_APPS=', Line) = 1) or (Pos('ANTHROPIC_API_KEY=', Line) = 1) or
    (Pos('GEMINI_API_KEY=', Line) = 1) or (Pos('OPENAI_API_KEY=', Line) = 1) or
    (Pos('# Ali sozlamalari', Line) = 1);
end;

{ Yangi kalit kiritilmagan bo'lsa (qayta o'rnatish) - eskisi saqlanadi }
function KeyValue(Old: TArrayOfString; Key, NewValue: String): String;
var
  I: Integer;
begin
  Result := Trim(NewValue);
  if Result <> '' then Exit;
  for I := 0 to GetArrayLength(Old) - 1 do
    if Pos(Key + '=', Old[I]) = 1 then
      Result := Copy(Old[I], Length(Key) + 2, MaxInt);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Dir, EnvFile, Groups: String;
  Old, Lines: TArrayOfString;
  I: Integer;
begin
  if CurStep <> ssPostInstall then Exit;
  Dir := ExpandConstant('{localappdata}\Ali');
  ForceDirectories(Dir);
  EnvFile := Dir + '\.env';
  SetArrayLength(Old, 0);
  if FileExists(EnvFile) then
    LoadStringsFromFile(EnvFile, Old);

  Groups := '';
  for I := 0 to GroupCount - 1 do
    if PermPage.Values[I] then
    begin
      if Groups <> '' then Groups := Groups + ',';
      Groups := Groups + GroupKey(I);
    end;

  SetArrayLength(Lines, 0);
  AddLine(Lines, '# Ali sozlamalari (o''rnatuvchi yozgan). Ruxsatlar birinchi ishga tushishda qo''llanadi.');
  AddLine(Lines, 'USER_NAME=' + Trim(NamePage.Values[0]));
  AddLine(Lines, 'ALI_INSTALL_GROUPS=' + Groups);
  AddLine(Lines, 'PLUGINS_OPEN_APPS=false');
  AddLine(Lines, 'ANTHROPIC_API_KEY=' + KeyValue(Old, 'ANTHROPIC_API_KEY', KeyPage.Values[0]));
  AddLine(Lines, 'GEMINI_API_KEY=' + KeyValue(Old, 'GEMINI_API_KEY', KeyPage.Values[1]));
  AddLine(Lines, 'OPENAI_API_KEY=' + KeyValue(Old, 'OPENAI_API_KEY', KeyPage.Values[2]));
  for I := 0 to GetArrayLength(Old) - 1 do
    if not IsManaged(Old[I]) then
      AddLine(Lines, Old[I]);
  SaveStringsToUTF8File(EnvFile, Lines, False);
end;
