# kotlinx.serialization keeps generated serializers
-keepattributes *Annotation*, InnerClasses
-keep,includedescriptorclasses class in.anylo.app.**$$serializer { *; }
-keepclassmembers class in.anylo.app.** { *** Companion; }
