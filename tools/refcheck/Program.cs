// refcheck — يتأكد إن كل نوع ودالة يستخدمها ملف dll (مثل NoxGame.dll) موجودة بمكتبات اللعبة.
// مكتبات اللعبة مقصوصة (Unity يشيل اللي ما تستخدمه)، فدالة موجودة بـ.NET العادي ممكن تكون ناقصة فيها.
// الاستخدام: dotnet run --project tools/refcheck -- <الملف.dll> "<مجلد اللعبة>/Scam With Your Friends_Data/Managed"
using Mono.Cecil;

var dll = args[0]; var managed = args[1];
var res = new DefaultAssemblyResolver(); res.AddSearchDirectory(managed);
foreach (var d in res.GetSearchDirectories().ToArray()) if (d != managed) res.RemoveSearchDirectory(d);
var m = ModuleDefinition.ReadModule(dll, new ReaderParameters { AssemblyResolver = res });
int bad = 0;
foreach (var t in m.GetTypeReferences()) { try { if (t.Resolve() == null) { Console.WriteLine("TYPE  " + t.FullName); bad++; } } catch (Exception e) { Console.WriteLine("TYPE! " + t.FullName + " " + e.Message); bad++; } }
foreach (var r in m.GetMemberReferences()) { try { if (r.Resolve() == null) { Console.WriteLine("MEMBER " + r.FullName); bad++; } } catch (Exception e) { Console.WriteLine("MEMBER! " + r.FullName + " " + e.Message); bad++; } }
Console.WriteLine($"missing: {bad}");
return bad == 0 ? 0 : 1;
