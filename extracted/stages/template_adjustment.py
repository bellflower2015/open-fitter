"""
Template adjustment stage - Template FBX不要版

Template FBXはプロプライエタリなため使用しない。
このステージは何も行わず、常にTrueを返す。
"""


class TemplateAdjustmentStage:
    """
    Template-specific corrections stage.
    
    Template FBXが利用不可能なため、このステージは何も行わない。
    常にTrueを返して次のステージに進む。
    """

    def __init__(self, processor):
        self.processor = processor

    def run(self):
        """
        Template調整を実行する。
        
        Template FBXが不要なため、何も行わずTrueを返す。
        """
        clothing_name = self.processor.ctx.clothing_avatar_data.get("name", None)
        if clothing_name == "Template":
            print("Templateからの変換: Template FBX不要モード（処理スキップ）")
        return True

