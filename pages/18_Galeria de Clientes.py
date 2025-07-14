# ========== EXIBIR GALERIA ==========

df, aba_clientes = carregar_dados()

if df.empty or "Foto" not in df.columns:
    st.info("Nenhuma imagem encontrada.")
else:
    df["Cliente"] = df["Cliente"].astype(str).str.strip()  # Remove espaços extras nos nomes
    nomes = sorted(df["Cliente"].dropna().unique())

    nome_filtrado = st.selectbox("Filtrar por cliente:", ["Todos"] + nomes)
    nome_filtrado = nome_filtrado.strip()  # Remove espaços antes/depois

    if nome_filtrado != "Todos":
        df = df[df["Cliente"].str.strip() == nome_filtrado]

    fotos_validas = df.dropna(subset=["Foto"])

    if fotos_validas.empty:
        st.warning("Nenhuma imagem disponível para esse filtro.")
    else:
        cols = st.columns(3)
        for i, (idx, row) in enumerate(fotos_validas.iterrows()):
            with cols[i % 3]:
                try:
                    response = requests.get(row["Foto"])
                    img = Image.open(BytesIO(response.content))
                    st.image(img, caption=row["Cliente"], use_container_width=True)
                except:
                    st.error(f"Erro ao carregar imagem de {row['Cliente']}")
                    continue

                with st.expander(f"🛠 Ações para {row['Cliente']}"):
                    if st.button(f"❌ Excluir imagem", key=f"excluir_{idx}"):
                        try:
                            cell = aba_clientes.find(str(row["Cliente"]).strip())
                            if cell:
                                col_foto = df.columns.get_loc("Foto") + 1
                                aba_clientes.update_cell(cell.row, col_foto, "")
                                st.success("✅ Imagem removida da planilha.")

                            if "res.cloudinary.com" in row["Foto"]:
                                nome_img = row["Foto"].split("/")[-1].split(".")[0]
                                public_id = f"Fotos clientes/{nome_img}"
                                cloudinary.uploader.destroy(public_id)
                                st.success("✅ Imagem deletada do Cloudinary com sucesso.")

                            st.experimental_rerun()
                        except Exception as e:
                            st.error(f"❌ Erro ao deletar imagem: {e}")

                    nova_foto = st.text_input("🔄 Substituir link da imagem", key=f"edit_{idx}")
                    if nova_foto:
                        try:
                            cell = aba_clientes.find(str(row["Cliente"]).strip())
                            if cell:
                                col_foto = df.columns.get_loc("Foto") + 1
                                aba_clientes.update_cell(cell.row, col_foto, nova_foto)
                                st.success("✅ Imagem substituída com sucesso.")
                                st.experimental_rerun()
                        except Exception as e:
                            st.error(f"❌ Erro ao substituir imagem: {e}")
